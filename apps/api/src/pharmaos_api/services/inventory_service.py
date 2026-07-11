"""Inventory (P1-M7): receiving by batch, adjustments, and the derived cache.

CLAUDE.md rules enforced here:
- Batches are the ONLY quantity truth; every change writes a stock_movement
  (never a bare UPDATE of quantity).
- branch_inventory.cached_quantity is DERIVED and updated in the SAME
  transaction as the movement; a rebuild command + drift check verify
  Invariant: cached_quantity == SUM(active batches' quantity).
- Receiving prefills from a 2D GS1 scan (GTIN/expiry/batch) — pack_serials
  persistence is Phase 2.
- Adjustments REQUIRE a reason and audit stock.adjusted; quarantining a batch
  audits batch.quarantined.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.audit import AuditAction
from pharmaos_api.errors import ApiError, ErrorCode
from pharmaos_api.models import Branch, Medication, MedicationBatch, StockMovement, User
from pharmaos_api.services import audit_service

_BATCH_STATUSES = {"active", "quarantined", "expired", "recalled", "depleted"}
MAX_PAGE_SIZE = 100
# Low-stock threshold: reorder point if set, else the minimum level (0 = untracked).
_LOW_THRESHOLD = "COALESCE(NULLIF(bi.reorder_point, 0), NULLIF(bi.min_stock_level, 0), 0)"


async def apply_cache_delta(
    session: AsyncSession, branch_id: uuid.UUID, medication_id: uuid.UUID, delta: Decimal
) -> None:
    """Upsert the derived cache row inside the CALLER's transaction (no commit)."""
    await session.execute(text("""
            INSERT INTO branch_inventory (branch_id, medication_id, cached_quantity)
            VALUES (:b, :m, :d)
            ON CONFLICT (branch_id, medication_id)
            DO UPDATE SET cached_quantity = branch_inventory.cached_quantity + :d
            """).bindparams(b=branch_id, m=medication_id, d=delta))


async def receive_stock(
    session: AsyncSession,
    *,
    actor: User,
    branch_id: uuid.UUID,
    medication_id: uuid.UUID,
    batch_number: str,
    expiry_date: dt.date,
    quantity: Decimal,
    purchase_price: Decimal,
    supplier_id: uuid.UUID | None = None,
) -> MedicationBatch:
    """Receive a batch: batch row + purchase_in movement + cache delta — one tx."""
    if quantity <= 0:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Quantity must be positive.")
    if purchase_price < 0:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Negative price.")
    if expiry_date <= dt.date.today():
        raise ApiError(ErrorCode.BATCH_EXPIRED, 422, message="Cannot receive expired stock.")

    # M11 hardening: validate references EXPLICITLY — an unknown id must be a
    # clean 422/404 for the UI, never a 500 from the FK violation.
    branch = await session.get(Branch, branch_id)
    if branch is None or branch.is_deleted or not branch.is_active:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Unknown branch.")
    medication = (
        await session.execute(
            select(Medication).where(
                Medication.id == medication_id, Medication.is_deleted.is_(False)
            )
        )
    ).scalar_one_or_none()
    if medication is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 404, message="Medication not found.")
    if supplier_id is not None:
        supplier_exists = (
            await session.execute(
                text("SELECT 1 FROM suppliers WHERE id = :s AND NOT is_deleted").bindparams(
                    s=supplier_id
                )
            )
        ).scalar_one_or_none()
        if supplier_exists is None:
            raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Unknown supplier.")

    batch = MedicationBatch(
        branch_id=branch_id,
        medication_id=medication_id,
        batch_number=batch_number,
        expiry_date=expiry_date,
        quantity=quantity,
        purchase_price=purchase_price,
        supplier_id=supplier_id,
        created_by=actor.id,
    )
    session.add(batch)
    await session.flush()
    session.add(
        StockMovement(
            branch_id=branch_id,
            batch_id=batch.id,
            movement_type="purchase_in",
            quantity_delta=quantity,
            reference_type="manual",
            created_by=actor.id,
        )
    )
    await apply_cache_delta(session, branch_id, medication_id, quantity)
    await session.commit()
    await session.refresh(batch)
    return batch


async def adjust_batch(
    session: AsyncSession,
    *,
    actor: User,
    batch: MedicationBatch,
    quantity_delta: Decimal,
    reason: str,
) -> MedicationBatch:
    """Manual adjustment (count correction/damage): movement + cache + audit — one tx."""
    if not reason.strip():
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Reason is required.")
    if quantity_delta == 0:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Zero adjustment.")
    if batch.quantity + quantity_delta < 0:
        raise ApiError(ErrorCode.STOCK_INSUFFICIENT, 409)

    # Only ACTIVE batches contribute to the derived cache. Adjusting a
    # quarantined/expired/recalled/depleted batch still moves the batch truth
    # (a stock_movement) but must NOT touch the cache, or the invariant drifts.
    was_active = batch.status == "active"
    batch.quantity = batch.quantity + quantity_delta
    if batch.quantity == 0 and batch.status == "active":
        batch.status = "depleted"
    batch.updated_by = actor.id
    session.add(
        StockMovement(
            branch_id=batch.branch_id,
            batch_id=batch.id,
            movement_type="adjustment",
            quantity_delta=quantity_delta,
            reference_type="manual",
            reason=reason.strip(),
            created_by=actor.id,
        )
    )
    if was_active:
        await apply_cache_delta(session, batch.branch_id, batch.medication_id, quantity_delta)
    await audit_service.record(
        session,
        AuditAction.STOCK_ADJUSTED,
        actor=actor,
        branch_id=batch.branch_id,
        entity_type="batch",
        entity_id=batch.id,
        metadata={"delta": str(quantity_delta), "reason": reason.strip()},
    )
    await session.commit()
    await session.refresh(batch)
    return batch


async def set_batch_status(
    session: AsyncSession, *, actor: User, batch: MedicationBatch, status: str, reason: str
) -> MedicationBatch:
    """Change batch status. Quarantine removes the batch's quantity from the
    derived cache (a quarantined batch is not sellable stock) and audits."""
    if status not in _BATCH_STATUSES:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Unknown status.")
    if status == batch.status:
        return batch

    was_countable = batch.status == "active"
    now_countable = status == "active"
    if was_countable and not now_countable:
        await apply_cache_delta(session, batch.branch_id, batch.medication_id, -batch.quantity)
        session.add(
            StockMovement(
                branch_id=batch.branch_id,
                batch_id=batch.id,
                movement_type="quarantine",
                quantity_delta=Decimal(0),  # physical qty unchanged; sellable stock changed
                reference_type="manual",
                reason=reason.strip() or status,
                created_by=actor.id,
            )
        )
    elif now_countable and not was_countable:
        await apply_cache_delta(session, batch.branch_id, batch.medication_id, batch.quantity)

    batch.status = status
    batch.updated_by = actor.id
    if status == "quarantined":
        await audit_service.record(
            session,
            AuditAction.BATCH_QUARANTINED,
            actor=actor,
            branch_id=batch.branch_id,
            entity_type="batch",
            entity_id=batch.id,
            metadata={"reason": reason.strip() or "manual"},
        )
    await session.commit()
    await session.refresh(batch)
    return batch


async def drift_check(session: AsyncSession, branch_id: uuid.UUID) -> list[dict[str, str]]:
    """Compare cache vs. truth. Returns drifted rows (empty = invariant holds)."""
    rows = (await session.execute(text("""
                SELECT COALESCE(c.medication_id, t.medication_id) AS medication_id,
                       COALESCE(c.cached_quantity, 0) AS cached,
                       COALESCE(t.truth, 0) AS truth
                FROM (SELECT medication_id, cached_quantity FROM branch_inventory
                      WHERE branch_id = :b AND NOT is_deleted) c
                FULL OUTER JOIN (
                    SELECT medication_id, SUM(quantity) AS truth FROM medication_batches
                    WHERE branch_id = :b AND NOT is_deleted AND status = 'active'
                    GROUP BY medication_id) t
                  ON t.medication_id = c.medication_id
                WHERE COALESCE(c.cached_quantity, 0) <> COALESCE(t.truth, 0)
                """).bindparams(b=branch_id))).all()
    return [{"medication_id": str(r[0]), "cached": str(r[1]), "truth": str(r[2])} for r in rows]


async def rebuild_cache(session: AsyncSession, branch_id: uuid.UUID) -> int:
    """Rebuild the derived cache from batch truth (periodic + at boot). Returns row count."""
    await session.execute(text("""
            INSERT INTO branch_inventory (branch_id, medication_id, cached_quantity)
            SELECT :b, medication_id, SUM(quantity) FROM medication_batches
            WHERE branch_id = :b AND NOT is_deleted AND status = 'active'
            GROUP BY medication_id
            ON CONFLICT (branch_id, medication_id)
            DO UPDATE SET cached_quantity = EXCLUDED.cached_quantity
            """).bindparams(b=branch_id))
    # Zero out cache rows whose truth disappeared (e.g. all batches quarantined).
    await session.execute(text("""
            UPDATE branch_inventory bi SET cached_quantity = 0
            WHERE bi.branch_id = :b AND bi.cached_quantity <> 0 AND NOT EXISTS (
                SELECT 1 FROM medication_batches mb
                WHERE mb.branch_id = :b AND mb.medication_id = bi.medication_id
                  AND NOT mb.is_deleted AND mb.status = 'active'
                GROUP BY mb.medication_id HAVING SUM(mb.quantity) <> 0)
            """).bindparams(b=branch_id))
    await session.commit()
    count = (
        await session.execute(
            text("SELECT COUNT(*) FROM branch_inventory WHERE branch_id = :b").bindparams(
                b=branch_id
            )
        )
    ).scalar_one()
    return int(count)


async def get_batch(session: AsyncSession, batch_id: uuid.UUID) -> MedicationBatch:
    batch = (
        await session.execute(
            select(MedicationBatch).where(
                MedicationBatch.id == batch_id, MedicationBatch.is_deleted.is_(False)
            )
        )
    ).scalar_one_or_none()
    if batch is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 404, message="Batch not found.")
    return batch


# --------------------------- read models (UI screens) ---------------------------


async def list_inventory(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    search: str | None = None,
    low_stock_only: bool = False,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, object]], int]:
    """Stock-on-hand per medication for a branch (reads the derived cache).

    Search reuses the catalog's Arabic normalization (trigram + ILIKE); low-stock
    ranks first so the reorder queue is always on top.
    """
    capped = min(max(limit, 1), MAX_PAGE_SIZE)
    where = ["bi.branch_id = :b", "NOT bi.is_deleted", "NOT m.is_deleted"]
    params: dict[str, object] = {"b": branch_id}
    if search and search.strip():
        where.append(
            "(normalize_arabic(m.trade_name_ar) % normalize_arabic(:q) "
            "OR m.trade_name ILIKE '%' || :q || '%' "
            "OR m.trade_name_ar ILIKE '%' || :q || '%')"
        )
        params["q"] = search.strip()
    if low_stock_only:
        where.append(f"({_LOW_THRESHOLD} > 0 AND bi.cached_quantity <= {_LOW_THRESHOLD})")
    where_sql = " AND ".join(where)

    total = (
        await session.execute(
            text(
                f"SELECT COUNT(*) FROM branch_inventory bi "  # noqa: S608 (fragments are constant)
                f"JOIN medications m ON m.id = bi.medication_id WHERE {where_sql}"
            ).bindparams(**params)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            text(
                f"""
                SELECT bi.medication_id, m.trade_name, m.trade_name_ar, bi.cached_quantity,
                       bi.min_stock_level, bi.reorder_point, bi.shelf_location,
                       ({_LOW_THRESHOLD} > 0
                        AND bi.cached_quantity <= {_LOW_THRESHOLD}) AS low_stock
                FROM branch_inventory bi JOIN medications m ON m.id = bi.medication_id
                WHERE {where_sql}
                ORDER BY low_stock DESC, m.trade_name
                OFFSET :skip LIMIT :lim
                """  # noqa: S608 (all interpolated fragments are constant; values are bound)
            ).bindparams(**params, skip=max(skip, 0), lim=capped)
        )
    ).all()
    return (
        [
            {
                "medication_id": str(r[0]),
                "trade_name": r[1],
                "trade_name_ar": r[2],
                "cached_quantity": str(r[3]),
                "min_stock_level": str(r[4]) if r[4] is not None else None,
                "reorder_point": str(r[5]) if r[5] is not None else None,
                "shelf_location": r[6],
                "low_stock": bool(r[7]),
            }
            for r in rows
        ],
        int(total),
    )


async def list_batches(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    medication_id: uuid.UUID | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[dict[str, object]], int]:
    """Batches for a branch, FEFO order (nearest expiry first). Carries the
    medication name so a branch-wide near-expiry view needs no extra lookups."""
    capped = min(max(limit, 1), MAX_PAGE_SIZE)
    conditions = [
        MedicationBatch.branch_id == branch_id,
        MedicationBatch.is_deleted.is_(False),
    ]
    if medication_id is not None:
        conditions.append(MedicationBatch.medication_id == medication_id)
    if status is not None:
        conditions.append(MedicationBatch.status == status)

    total = (
        await session.execute(select(func.count(MedicationBatch.id)).where(*conditions))
    ).scalar_one()
    rows = (
        await session.execute(
            select(
                MedicationBatch,
                Medication.trade_name,
                Medication.trade_name_ar,
            )
            .join(Medication, Medication.id == MedicationBatch.medication_id)
            .where(*conditions)
            .order_by(MedicationBatch.expiry_date, MedicationBatch.received_at)
            .offset(max(skip, 0))
            .limit(capped)
        )
    ).all()
    return [
        {
            "id": str(b.id),
            "branch_id": str(b.branch_id),
            "medication_id": str(b.medication_id),
            "trade_name": trade_name,
            "trade_name_ar": trade_name_ar,
            "batch_number": b.batch_number,
            "expiry_date": b.expiry_date.isoformat(),
            "quantity": str(b.quantity),
            "purchase_price": str(b.purchase_price),
            "supplier_id": str(b.supplier_id) if b.supplier_id else None,
            "status": b.status,
            "received_at": b.received_at.isoformat(),
        }
        for b, trade_name, trade_name_ar in rows
    ], int(total)


async def list_branches_min(session: AsyncSession) -> list[dict[str, str]]:
    """Minimal active-branch list for operational branch selection (inventory is
    branch-scoped). Distinct from the settings-guarded branch config endpoint."""
    rows = (
        await session.execute(
            select(Branch.id, Branch.name, Branch.currency_code)
            .where(Branch.is_deleted.is_(False), Branch.is_active.is_(True))
            .order_by(Branch.name)
        )
    ).all()
    return [{"id": str(r[0]), "name": r[1], "currency_code": r[2]} for r in rows]


# ------------------------------ suppliers (minimal) ------------------------------


async def list_suppliers(session: AsyncSession) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            text("SELECT id, name FROM suppliers WHERE NOT is_deleted ORDER BY name")
        )
    ).all()
    return [{"id": str(r[0]), "name": r[1]} for r in rows]


async def create_supplier(session: AsyncSession, *, actor: User, name: str) -> dict[str, str]:
    """Minimal (Q2) supplier: name only. Full supplier management is Phase 2."""
    clean = name.strip()
    if not clean:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Supplier name is required.")
    row = (
        await session.execute(
            text(
                "INSERT INTO suppliers (name, created_by, updated_by) "
                "VALUES (:n, :a, :a) RETURNING id, name"
            ).bindparams(n=clean, a=actor.id)
        )
    ).one()
    await session.commit()
    return {"id": str(row[0]), "name": row[1]}


# --------------------------- expiry sweep (M11) ---------------------------


async def expiry_sweep(session: AsyncSession) -> dict[str, int]:
    """Mark past-expiry ACTIVE batches as 'expired' and remove their quantity
    from the derived cache — expired stock must never look sellable on any
    screen. Runs at boot and via the CLI (cron-able on the device).

    Ledger: one expiry_writeoff movement per swept batch (delta 0 — the
    physical quantity is unchanged; the SELLABLE stock changed, same convention
    as quarantine). The sale path already refuses expired batches by date; the
    sweep aligns statuses and the cache with that reality.
    """
    today = dt.date.today()
    batches = list(
        (
            await session.execute(
                select(MedicationBatch)
                .where(
                    MedicationBatch.is_deleted.is_(False),
                    MedicationBatch.status == "active",
                    MedicationBatch.expiry_date < today,
                )
                .with_for_update()
            )
        ).scalars()
    )
    for batch in batches:
        if batch.quantity > 0:
            await apply_cache_delta(session, batch.branch_id, batch.medication_id, -batch.quantity)
        session.add(
            StockMovement(
                branch_id=batch.branch_id,
                batch_id=batch.id,
                movement_type="expiry_writeoff",
                quantity_delta=Decimal(0),  # physical qty unchanged; sellable stock changed
                reference_type="system",
                reason="expiry_sweep",
            )
        )
        batch.status = "expired"
    if batches:
        await session.commit()
    return {"swept": len(batches)}


# ------------------------------ boot-time integrity ------------------------------


async def boot_check_and_heal(session: AsyncSession) -> dict[str, dict[str, object]]:
    """At app boot: sweep past-expiry batches, then verify
    cached_quantity == SUM(active batches) for every branch and self-heal any
    drift by rebuilding from batch truth (the cache is derived, so a rebuild is
    always safe). Returns a per-branch summary for the boot log."""
    swept = await expiry_sweep(session)
    branch_ids = (
        (await session.execute(select(Branch.id).where(Branch.is_deleted.is_(False))))
        .scalars()
        .all()
    )
    summary: dict[str, dict[str, object]] = {}
    for branch_id in branch_ids:
        drift = await drift_check(session, branch_id)
        if drift:
            await rebuild_cache(session, branch_id)
        summary[str(branch_id)] = {"drifted": len(drift), "healed": bool(drift)}
    summary["_expiry_sweep"] = {"swept": swept["swept"]}
    return summary
