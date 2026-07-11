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

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.audit import AuditAction
from pharmaos_api.errors import ApiError, ErrorCode
from pharmaos_api.models import MedicationBatch, StockMovement, User
from pharmaos_api.services import audit_service

_BATCH_STATUSES = {"active", "quarantined", "expired", "recalled", "depleted"}


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
