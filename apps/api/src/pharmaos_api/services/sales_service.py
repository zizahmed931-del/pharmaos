"""Walking-skeleton sale flow (Phase 0 / M12).

One ATOMIC transaction covers: barcode resolution -> unit conversion ->
FEFO batch picking -> batch decrement + stock_movements entries ->
invoice + invoice_items. A crash mid-sale persists NOTHING (offline
correctness: no partial invoices — CLAUDE.md crash-recovery requirement).

Inventory rules enforced here (CLAUDE.md):
- batches are the only quantity truth; every change writes a stock_movement
- quantities converted to the SMALLEST unit via medication_packaging
- FEFO: nearest expiry first
- no sale from a batch with status != 'active' or an expired batch (E-STK-002)
- insufficient stock -> E-STK-001, nothing persisted
"""

import datetime as dt
import uuid
from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.audit import AuditAction
from pharmaos_api.errors import ApiError, ErrorCode
from pharmaos_api.gs1 import Gs1ParseError, parse_gs1
from pharmaos_api.models import (
    Branch,
    Invoice,
    InvoiceItem,
    Medication,
    MedicationBarcode,
    MedicationBatch,
    MedicationPackaging,
    StockMovement,
    User,
)
from pharmaos_api.services import (
    audit_service,
    cashier_service,
    catalog_service,
    customer_service,
    pack_serial_service,
)


@dataclass(frozen=True)
class ScanResult:
    medication_id: uuid.UUID
    trade_name: str
    trade_name_ar: str | None
    packaging_id: uuid.UUID
    packaging_name_ar: str
    level: int
    selling_price: Decimal
    requires_prescription: bool
    controlled_substance: bool


@dataclass(frozen=True)
class SaleLine:
    """One cart line (M8 POS).

    Identification — one of:
    - barcode only: the scanned/default packaging level (skeleton behavior);
    - barcode + packaging_id: POS unit switching — the cashier scanned the pack
      but sells a different level (box/strip/tablet) of the SAME medication;
    - medication_id + packaging_id: name-search line (no barcode on hand).
    """

    quantity: Decimal  # at the sold packaging level
    barcode: str | None = None
    medication_id: uuid.UUID | None = None
    packaging_id: uuid.UUID | None = None


def _scan_result(medication: Medication, packaging: MedicationPackaging) -> ScanResult:
    return ScanResult(
        medication_id=medication.id,
        trade_name=medication.trade_name,
        trade_name_ar=medication.trade_name_ar,
        packaging_id=packaging.id,
        packaging_name_ar=packaging.name_ar,
        level=packaging.level,
        selling_price=packaging.selling_price,
        requires_prescription=medication.requires_prescription,
        controlled_substance=medication.controlled_substance,
    )


async def resolve_barcode(session: AsyncSession, barcode: str) -> ScanResult:
    """Exact barcode match — the fastest POS path (indexed; scan->display < 50ms)."""
    stmt = (
        select(MedicationBarcode, Medication)
        .join(Medication, Medication.id == MedicationBarcode.medication_id)
        .where(
            MedicationBarcode.barcode == barcode,
            MedicationBarcode.is_deleted.is_(False),
            Medication.is_deleted.is_(False),
            Medication.is_active.is_(True),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 404, message="Unknown barcode.")
    barcode_row, medication = row

    packaging = await _resolve_sale_packaging(session, medication.id, barcode_row.packaging_id)
    return _scan_result(medication, packaging)


async def resolve_scan_code(session: AsyncSession, code: str) -> ScanResult:
    """POS scan entry point: exact barcode first (fast path), then a GS1
    DataMatrix fallback — Egyptian packs carry 2D codes (EDA track & trace),
    so a POS scanner may hand us a full GS1 element string instead of an EAN13.
    The embedded GTIN resolves via medications.gtin or a stored barcode."""
    try:
        return await resolve_barcode(session, code)
    except ApiError as unknown_barcode:
        try:
            pack = parse_gs1(code)
        except Gs1ParseError:
            raise unknown_barcode from None
        if pack.gtin is None:
            raise unknown_barcode from None
        medication = await catalog_service.find_by_gtin(session, pack.gtin)
        if medication is None or not medication.is_active:
            raise unknown_barcode from None
        packaging = await _resolve_sale_packaging(session, medication.id, None)
        return _scan_result(medication, packaging)


async def _get_sellable_packaging_of(
    session: AsyncSession, medication_id: uuid.UUID, packaging_id: uuid.UUID
) -> MedicationPackaging:
    """A packaging override is only valid for the SAME medication and must be
    sellable — a foreign or retired level would silently sell the wrong item."""
    packaging = await session.get(MedicationPackaging, packaging_id)
    if (
        packaging is None
        or packaging.is_deleted
        or packaging.medication_id != medication_id
        or not packaging.is_sellable
    ):
        raise ApiError(
            ErrorCode.VALIDATION_FAILED,
            422,
            message="Packaging level does not belong to this medication or is not sellable.",
        )
    return packaging


async def _resolve_line(session: AsyncSession, line: SaleLine) -> ScanResult:
    """Resolve a SaleLine to its medication + sold packaging level (see SaleLine)."""
    if line.barcode:
        scan = await resolve_barcode(session, line.barcode)
        if line.packaging_id is None or line.packaging_id == scan.packaging_id:
            return scan
        packaging = await _get_sellable_packaging_of(session, scan.medication_id, line.packaging_id)
        return replace(
            scan,
            packaging_id=packaging.id,
            packaging_name_ar=packaging.name_ar,
            level=packaging.level,
            selling_price=packaging.selling_price,
        )

    if line.medication_id is None or line.packaging_id is None:
        raise ApiError(
            ErrorCode.VALIDATION_FAILED,
            422,
            message="Sale line needs a barcode or medication_id + packaging_id.",
        )
    medication = (
        await session.execute(
            select(Medication).where(
                Medication.id == line.medication_id,
                Medication.is_deleted.is_(False),
                Medication.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if medication is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 404, message="Unknown medication.")
    packaging = await _get_sellable_packaging_of(session, medication.id, line.packaging_id)
    return _scan_result(medication, packaging)


async def _resolve_sale_packaging(
    session: AsyncSession, medication_id: uuid.UUID, packaging_id: uuid.UUID | None
) -> MedicationPackaging:
    """Barcode-linked level wins; otherwise the medication's default sale level."""
    if packaging_id is not None:
        packaging = await session.get(MedicationPackaging, packaging_id)
        if packaging is not None and not packaging.is_deleted and packaging.is_sellable:
            return packaging
    stmt = (
        select(MedicationPackaging)
        .where(
            MedicationPackaging.medication_id == medication_id,
            MedicationPackaging.is_deleted.is_(False),
            MedicationPackaging.is_sellable.is_(True),
        )
        .order_by(MedicationPackaging.is_default_sale.desc(), MedicationPackaging.level)
        .limit(1)
    )
    packaging = (await session.execute(stmt)).scalar_one_or_none()
    if packaging is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="No sellable packaging level.")
    return packaging


async def _smallest_unit_factor(
    session: AsyncSession, medication_id: uuid.UUID, level: int
) -> Decimal:
    """How many smallest units one unit of `level` contains.

    factor(level) = product of qty_in_parent over all DEEPER levels
    (box=1: strips/box x tablets/strip; tablet=deepest: 1).
    """
    stmt = (
        select(MedicationPackaging.level, MedicationPackaging.qty_in_parent)
        .where(
            MedicationPackaging.medication_id == medication_id,
            MedicationPackaging.is_deleted.is_(False),
            MedicationPackaging.level > level,
        )
        .order_by(MedicationPackaging.level)
    )
    factor = Decimal(1)
    for deeper_level, qty_in_parent in (await session.execute(stmt)).all():
        if qty_in_parent is None:
            raise ApiError(
                ErrorCode.VALIDATION_FAILED,
                422,
                message=f"qty_in_parent missing for packaging level {deeper_level}.",
            )
        factor *= Decimal(qty_in_parent)
    return factor


async def _next_invoice_number(session: AsyncSession, branch_id: uuid.UUID) -> str:
    """Skeleton numbering: INV-YYYYMMDD-NNNN per branch per day.

    LOCAL device date — the pharmacy's daily sequence resets at local
    midnight (cash sessions and Z-reports are local-day concepts).
    The UNIQUE(branch_id, invoice_number) constraint is the correctness
    backstop; on a rare collision the client re-submits the sale.
    """
    today = dt.date.today().strftime("%Y%m%d")
    prefix = f"INV-{today}-"
    stmt = select(func.count(Invoice.id)).where(
        Invoice.branch_id == branch_id, Invoice.invoice_number.like(prefix + "%")
    )
    count = (await session.execute(stmt)).scalar_one()
    return f"{prefix}{count + 1:04d}"


async def create_sale(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    lines: list[SaleLine],
    cashier: User,
    payment_method: str = "cash",
    tendered: Decimal | None = None,
    serials: list[str] | None = None,
    customer_id: uuid.UUID | None = None,
) -> Invoice:
    """Create a completed sale invoice in ONE transaction (see module docstring).

    M10: the invoice links to the seller's OPEN cash session when one exists
    (sales without a session stay legal — a pharmacist holds sales.create but
    not cashier.open_session). `tendered` persists the customer cash math
    (cash only; change = tendered − total).
    """
    if not lines:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Empty sale.")

    branch = await session.get(Branch, branch_id)
    if branch is None or branch.is_deleted or not branch.is_active:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Unknown branch.")

    # Expiry is a LOCAL-date concept: a batch expired "yesterday" on the
    # pharmacy's clock must not sell, even while UTC is still on that date
    # (Egypt is UTC+2/+3 — a UTC date check would allow post-expiry sales
    # for a few hours after midnight).
    today = dt.date.today()
    subtotal = Decimal("0.00")
    pending_items: list[InvoiceItem] = []
    pending_movements: list[StockMovement] = []

    for line in lines:
        if line.quantity <= 0:
            raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Quantity must be positive.")
        scan = await _resolve_line(session, line)
        factor = await _smallest_unit_factor(session, scan.medication_id, scan.level)
        needed = (line.quantity * factor).quantize(Decimal("0.001"))

        # FEFO: nearest expiry first; lock candidate rows for this transaction.
        stmt = (
            select(MedicationBatch)
            .where(
                MedicationBatch.branch_id == branch_id,
                MedicationBatch.medication_id == scan.medication_id,
                MedicationBatch.is_deleted.is_(False),
                MedicationBatch.status == "active",
                MedicationBatch.expiry_date >= today,
                MedicationBatch.quantity > 0,
            )
            .order_by(MedicationBatch.expiry_date, MedicationBatch.received_at)
            .with_for_update()
        )
        batches = list((await session.execute(stmt)).scalars())
        available = sum((b.quantity for b in batches), Decimal(0))

        if available < needed:
            # Distinguish "nothing valid but blocked stock exists" (E-STK-002).
            blocked_stmt = select(func.count(MedicationBatch.id)).where(
                MedicationBatch.branch_id == branch_id,
                MedicationBatch.medication_id == scan.medication_id,
                MedicationBatch.is_deleted.is_(False),
                MedicationBatch.quantity > 0,
                (MedicationBatch.status != "active") | (MedicationBatch.expiry_date < today),
            )
            blocked = (await session.execute(blocked_stmt)).scalar_one()
            code = ErrorCode.BATCH_EXPIRED if blocked > 0 else ErrorCode.STOCK_INSUFFICIENT
            raise ApiError(code, 409)

        line_total = (line.quantity * scan.selling_price).quantize(Decimal("0.01"))
        subtotal += line_total
        remaining = needed
        for batch in batches:
            if remaining <= 0:
                break
            slice_qty = min(batch.quantity, remaining)
            batch.quantity = batch.quantity - slice_qty
            if batch.quantity == 0:
                batch.status = "depleted"
            remaining -= slice_qty

            # Display quantity proportional to the slice (exact when one batch covers it).
            slice_display = (line.quantity * slice_qty / needed).quantize(Decimal("0.001"))
            slice_total = (line_total * slice_qty / needed).quantize(Decimal("0.01"))
            pending_items.append(
                InvoiceItem(
                    branch_id=branch_id,
                    medication_id=scan.medication_id,
                    packaging_id=scan.packaging_id,
                    batch_id=batch.id,
                    quantity=slice_display,
                    qty_smallest=slice_qty,
                    unit_price=scan.selling_price,
                    line_total=slice_total,
                    created_by=cashier.id,
                )
            )
            pending_movements.append(
                StockMovement(
                    branch_id=branch_id,
                    batch_id=batch.id,
                    movement_type="sale_out",
                    quantity_delta=-slice_qty,
                    reference_type="invoice",
                    created_by=cashier.id,
                )
            )
            # Derived cache maintained in the SAME transaction (CLAUDE.md).
            from pharmaos_api.services.inventory_service import apply_cache_delta

            await apply_cache_delta(session, branch_id, scan.medication_id, -slice_qty)

    total = subtotal  # discount 0 / tax 0 in the skeleton (tax profiles: Phase 2)

    # M10 — customer cash carry-through (validated against the AUTHORITATIVE total).
    tendered_amount: Decimal | None = None
    change_amount: Decimal | None = None
    if tendered is not None:
        if payment_method != "cash":
            raise ApiError(
                ErrorCode.VALIDATION_FAILED, 422, message="Tendered applies to cash sales only."
            )
        tendered_amount = tendered.quantize(Decimal("0.01"))
        if tendered_amount < total:
            raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Tendered is below the total.")
        change_amount = (tendered_amount - total).quantize(Decimal("0.01"))

    # M10 — attach the seller's open drawer session (if any) for the Z-report.
    open_session = await cashier_service.get_open_session(
        session, branch_id=branch_id, cashier_id=cashier.id
    )

    invoice = Invoice(
        branch_id=branch_id,
        invoice_number=await _next_invoice_number(session, branch_id),
        invoice_type="retail",
        status="completed",
        currency_code=branch.currency_code,
        subtotal=subtotal,
        discount_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total=total,
        payment_method=payment_method,
        cash_session_id=open_session.id if open_session is not None else None,
        tendered_amount=tendered_amount,
        change_amount=change_amount,
        created_by=cashier.id,
    )
    session.add(invoice)
    try:
        await session.flush()
    except IntegrityError as exc:
        # UNIQUE(branch_id, invoice_number) backstop fired (rare on a single
        # device). The rollback discards EVERYTHING (atomicity) — the client
        # simply re-submits the sale.
        await session.rollback()
        raise ApiError(
            ErrorCode.SYNC_CONFLICT, 409, message="Invoice number collision — retry the sale."
        ) from exc

    for item in pending_items:
        item.invoice_id = invoice.id
    for movement in pending_movements:
        movement.reference_id = invoice.id
    session.add_all(pending_items)
    session.add_all(pending_movements)

    # P2-M3: link scanned 2D pack serials to this invoice (dispensed) — atomic
    # with the sale, so an unknown/already-dispensed serial rolls it ALL back.
    if serials:
        await pack_serial_service.link_dispensed(
            session,
            actor=cashier,
            branch_id=branch_id,
            invoice_id=invoice.id,
            serials=serials,
        )

    # P2-M5: attach the customer and accrue loyalty points — atomic with the
    # sale (an unknown/inactive customer rolls the whole sale back). Validation
    # happens in accrue_for_sale before we set the FK, so the customer_id link
    # can never violate the constraint at commit.
    if customer_id is not None:
        await customer_service.accrue_for_sale(
            session,
            cashier=cashier,
            customer_id=customer_id,
            invoice_id=invoice.id,
            total=total,
        )
        invoice.customer_id = customer_id

    # Audit the sale IN THE SAME transaction (CLAUDE.md: audit from the first
    # write). If the commit fails, the audit entry rolls back with the sale.
    await audit_service.record(
        session,
        AuditAction.INVOICE_CREATED,
        actor=cashier,
        branch_id=branch_id,
        entity_type="invoice",
        entity_id=invoice.id,
        metadata={
            "invoice_number": invoice.invoice_number,
            "total": str(invoice.total),
            "currency_code": invoice.currency_code,
            "line_count": len(pending_items),
        },
    )

    await session.commit()  # ONE atomic unit: batches + movements + invoice + items + audit
    await session.refresh(invoice)
    return invoice
