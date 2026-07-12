"""Pack serials (P2-M3): per-pack GS1 serial capture + dispense linkage.

EDA track & trace (decrees 161/475/2025): every 2D pack carries GTIN + expiry +
batch + a random serial. We persist those serials on RECEIVE (linked to the
batch) and mark them DISPENSED (linked to the invoice) on sale — the trail the
national-reporting module (P2-M11, tt_events) will submit.

Both mutating functions run inside the CALLER's transaction (no commit):
receiving is atomic with the batch, dispensing is atomic with the invoice. A
duplicate (gtin, serial_number) is rejected — decree 804 defines a duplicate
serial as a "non-compliant product" (E-TT-002).
"""

import uuid

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.errors import ApiError, ErrorCode
from pharmaos_api.models import MedicationBatch, PackSerial, User

MAX_PAGE_SIZE = 100


def _clean(serials: list[str]) -> list[str]:
    """Trim, drop blanks, de-duplicate within the request (order-preserving)."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in serials:
        value = raw.strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


async def capture_received(
    session: AsyncSession,
    *,
    actor: User,
    batch: MedicationBatch,
    gtin: str | None,
    serials: list[str],
) -> int:
    """Persist scanned pack serials for a just-received batch (no commit).

    Returns the count captured. Requires a GTIN when serials are present. A
    duplicate (gtin, serial) rolls the whole receive back with E-TT-002."""
    clean = _clean(serials)
    if not clean:
        return 0
    code = (gtin or "").strip()
    if not code:
        raise ApiError(
            ErrorCode.VALIDATION_FAILED, 422, message="GTIN is required to capture pack serials."
        )
    for serial in clean:
        session.add(
            PackSerial(
                branch_id=batch.branch_id,
                batch_id=batch.id,
                serial_number=serial,
                gtin=code,
                status="in_stock",
                tt_report_status="pending",
                created_by=actor.id,
                updated_by=actor.id,
            )
        )
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ApiError(
            ErrorCode.PACK_SERIAL_DUPLICATE, 409, message="Duplicate pack serial (GTIN + serial)."
        ) from exc
    return len(clean)


async def link_dispensed(
    session: AsyncSession,
    *,
    actor: User,
    branch_id: uuid.UUID,
    invoice_id: uuid.UUID,
    serials: list[str],
) -> int:
    """Mark scanned serials dispensed and link them to the invoice (no commit).

    Each serial must be in_stock in this branch — otherwise the sale is rejected
    (422; the enclosing transaction rolls back so nothing persists)."""
    clean = _clean(serials)
    for serial in clean:
        pack = (
            await session.execute(
                select(PackSerial)
                .where(
                    PackSerial.branch_id == branch_id,
                    PackSerial.serial_number == serial,
                    PackSerial.status == "in_stock",
                    PackSerial.is_deleted.is_(False),
                )
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if pack is None:
            raise ApiError(
                ErrorCode.VALIDATION_FAILED,
                422,
                message="Unknown or already-dispensed pack serial.",
            )
        pack.status = "dispensed"
        pack.dispensed_invoice_id = invoice_id
        pack.updated_by = actor.id
    return len(clean)


async def list_serials(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    batch_id: uuid.UUID | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, object]], int]:
    capped = min(max(limit, 1), MAX_PAGE_SIZE)
    conditions: list[ColumnElement[bool]] = [
        PackSerial.branch_id == branch_id,
        PackSerial.is_deleted.is_(False),
    ]
    if batch_id is not None:
        conditions.append(PackSerial.batch_id == batch_id)
    if status is not None:
        conditions.append(PackSerial.status == status)
    total = (
        await session.execute(select(func.count(PackSerial.id)).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                select(PackSerial)
                .where(*conditions)
                .order_by(PackSerial.created_at.desc())
                .offset(max(skip, 0))
                .limit(capped)
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(p.id),
            "batch_id": str(p.batch_id),
            "serial_number": p.serial_number,
            "gtin": p.gtin,
            "status": p.status,
            "dispensed_invoice_id": str(p.dispensed_invoice_id) if p.dispensed_invoice_id else None,
            "tt_report_status": p.tt_report_status,
        }
        for p in rows
    ], int(total)
