"""Cash sessions (P1-M10): open/close, drawer math, and the Z-report.

Rules:
- ONE open session per cashier per branch (service check + partial unique
  index backstop for races — same pattern as invoice numbering).
- Drawer math: expected_cash = opening_float + Σ(total of CASH invoices linked
  to the session). Tendered/change cancel out (tendered in, change back out —
  the drawer nets +total), so they are recorded on invoices for the customer
  math but do not enter the expected-cash formula.
- Close FREEZES expected/counted/discrepancy on the row — a shift's Z numbers
  never drift when later data changes. cash_session.closed is audited in the
  SAME transaction; a nonzero discrepancy is additionally recorded via
  record_independent AFTER commit (audit_service: incident events persist
  regardless of the surrounding operation).
- Day filtering uses the DATABASE's date cast of created_at/opened_at — the
  device runs in the pharmacy's local timezone, matching the local-day
  invoice-numbering convention (INV-YYYYMMDD-…).
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.audit import AuditAction
from pharmaos_api.errors import ApiError, ErrorCode
from pharmaos_api.models import Branch, CashSession, User
from pharmaos_api.services import audit_service

_ZERO = Decimal("0.00")


def _q2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


async def get_open_session(
    session: AsyncSession, *, branch_id: uuid.UUID, cashier_id: uuid.UUID
) -> CashSession | None:
    """The cashier's open drawer in this branch (used by the sale flow — no commit)."""
    return (
        await session.execute(
            select(CashSession).where(
                CashSession.branch_id == branch_id,
                CashSession.cashier_id == cashier_id,
                CashSession.status == "open",
                CashSession.is_deleted.is_(False),
            )
        )
    ).scalar_one_or_none()


async def get_session(session: AsyncSession, session_id: uuid.UUID) -> CashSession:
    row = (
        await session.execute(
            select(CashSession).where(
                CashSession.id == session_id, CashSession.is_deleted.is_(False)
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 404, message="Cash session not found.")
    return row


async def open_session(
    session: AsyncSession, *, actor: User, branch_id: uuid.UUID, opening_float: Decimal
) -> CashSession:
    if opening_float < 0:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Negative opening float.")
    branch = await session.get(Branch, branch_id)
    if branch is None or branch.is_deleted or not branch.is_active:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Unknown branch.")
    if await get_open_session(session, branch_id=branch_id, cashier_id=actor.id) is not None:
        raise ApiError(ErrorCode.SESSION_ALREADY_OPEN, 409)

    row = CashSession(
        branch_id=branch_id,
        cashier_id=actor.id,
        opening_float=_q2(opening_float),
        created_by=actor.id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as exc:  # partial-unique backstop (open race)
        await session.rollback()
        raise ApiError(ErrorCode.SESSION_ALREADY_OPEN, 409) from exc
    await audit_service.record(
        session,
        AuditAction.CASH_SESSION_OPENED,
        actor=actor,
        branch_id=branch_id,
        entity_type="cash_session",
        entity_id=row.id,
        metadata={"opening_float": str(_q2(opening_float))},
    )
    await session.commit()
    await session.refresh(row)
    return row


async def session_summary(session: AsyncSession, cash_session: CashSession) -> dict[str, str | int]:
    """Live drawer summary for one session (completed invoices only)."""
    rows = (await session.execute(text("""
                SELECT payment_method, COUNT(*) AS n, COALESCE(SUM(total), 0) AS amount,
                       COALESCE(SUM(tendered_amount), 0) AS tendered,
                       COALESCE(SUM(change_amount), 0) AS change
                FROM invoices
                WHERE cash_session_id = :s AND NOT is_deleted AND status = 'completed'
                GROUP BY payment_method
                """).bindparams(s=cash_session.id))).all()
    stats = {r[0]: r for r in rows}
    cash = stats.get("cash")
    card = stats.get("card")
    cash_total = Decimal(cash[2]) if cash else _ZERO
    expected = _q2(cash_session.opening_float + cash_total)
    return {
        "cash_count": int(cash[1]) if cash else 0,
        "cash_total": str(_q2(cash_total)),
        "card_count": int(card[1]) if card else 0,
        "card_total": str(_q2(Decimal(card[2]))) if card else str(_ZERO),
        "tendered_total": str(_q2(Decimal(cash[3]))) if cash else str(_ZERO),
        "change_total": str(_q2(Decimal(cash[4]))) if cash else str(_ZERO),
        "expected_cash": str(expected),
    }


async def close_session(
    session: AsyncSession,
    *,
    actor: User,
    cash_session: CashSession,
    counted_cash: Decimal,
    notes: str | None = None,
) -> CashSession:
    """Close the drawer: freeze expected/counted/discrepancy + audit.

    cashier.close_session belongs to super_admin/branch_manager (the matrix) —
    the router enforces it; the service accepts any actor so the CLI/tests can
    exercise the flow directly.
    """
    if cash_session.status != "open":
        raise ApiError(ErrorCode.SESSION_NOT_OPEN, 409)
    if counted_cash < 0:
        raise ApiError(ErrorCode.VALIDATION_FAILED, 422, message="Negative counted cash.")

    summary = await session_summary(session, cash_session)
    expected = Decimal(str(summary["expected_cash"]))
    counted = _q2(counted_cash)
    discrepancy = _q2(counted - expected)

    cash_session.status = "closed"
    cash_session.closed_at = dt.datetime.now(dt.UTC)
    cash_session.closed_by = actor.id
    cash_session.expected_cash = expected
    cash_session.counted_cash = counted
    cash_session.discrepancy = discrepancy
    cash_session.closing_notes = notes.strip() if notes and notes.strip() else None
    cash_session.updated_by = actor.id

    metadata = {
        "expected_cash": str(expected),
        "counted_cash": str(counted),
        "discrepancy": str(discrepancy),
        "cash_total": str(summary["cash_total"]),
        "card_total": str(summary["card_total"]),
    }
    await audit_service.record(
        session,
        AuditAction.CASH_SESSION_CLOSED,
        actor=actor,
        branch_id=cash_session.branch_id,
        entity_type="cash_session",
        entity_id=cash_session.id,
        metadata=metadata,
    )
    await session.commit()
    await session.refresh(cash_session)

    if discrepancy != 0:
        # Incident event — its own transaction, after the close is durable
        # (audit_service doc: discrepancy must be recorded regardless).
        await audit_service.record_independent(
            AuditAction.CASH_SESSION_DISCREPANCY,
            actor=actor,
            branch_id=cash_session.branch_id,
            entity_type="cash_session",
            entity_id=cash_session.id,
            metadata=metadata,
        )
    return cash_session


async def list_sessions(
    session: AsyncSession,
    *,
    branch_id: uuid.UUID,
    day: dt.date | None = None,
    status: str | None = None,
) -> list[dict[str, object]]:
    """Sessions for the manager view (cashier name joined), newest first."""
    where = ["cs.branch_id = :b", "NOT cs.is_deleted"]
    params: dict[str, object] = {"b": branch_id}
    if day is not None:
        where.append("CAST(cs.opened_at AS date) = :d")
        params["d"] = day
    if status is not None:
        where.append("cs.status = :st")
        params["st"] = status
    rows = (
        await session.execute(text(f"""
                SELECT cs.id, cs.status, cs.opening_float, cs.opened_at, cs.closed_at,
                       cs.expected_cash, cs.counted_cash, cs.discrepancy, cs.closing_notes,
                       u.username, u.full_name
                FROM cash_sessions cs JOIN users u ON u.id = cs.cashier_id
                WHERE {" AND ".join(where)}
                ORDER BY cs.opened_at DESC
                LIMIT 100
                """).bindparams(**params))  # noqa: S608 (fragments are constant; values are bound)
    ).all()
    return [
        {
            "id": str(r[0]),
            "status": r[1],
            "opening_float": str(r[2]),
            "opened_at": r[3].isoformat(),
            "closed_at": r[4].isoformat() if r[4] else None,
            "expected_cash": str(r[5]) if r[5] is not None else None,
            "counted_cash": str(r[6]) if r[6] is not None else None,
            "discrepancy": str(r[7]) if r[7] is not None else None,
            "closing_notes": r[8],
            "cashier_username": r[9],
            "cashier_full_name": r[10],
        }
        for r in rows
    ]


async def day_report(
    session: AsyncSession, *, branch_id: uuid.UUID, day: dt.date
) -> dict[str, object]:
    """End-of-day Z-report: the branch's local-day totals by payment method,
    split between in-session sales and sales made outside any drawer session
    (e.g. a pharmacist selling without cashier.open_session)."""
    rows = (await session.execute(text("""
                SELECT payment_method,
                       (cash_session_id IS NOT NULL) AS in_session,
                       COUNT(*) AS n, COALESCE(SUM(total), 0) AS amount
                FROM invoices
                WHERE branch_id = :b AND NOT is_deleted AND status = 'completed'
                  AND CAST(created_at AS date) = :d
                GROUP BY payment_method, (cash_session_id IS NOT NULL)
                """).bindparams(b=branch_id, d=day))).all()

    def _bucket(method: str, in_session: bool) -> tuple[int, Decimal]:
        for r in rows:
            if r[0] == method and bool(r[1]) == in_session:
                return int(r[2]), _q2(Decimal(r[3]))
        return 0, _ZERO

    cash_in_n, cash_in = _bucket("cash", True)
    card_in_n, card_in = _bucket("card", True)
    cash_out_n, cash_out = _bucket("cash", False)
    card_out_n, card_out = _bucket("card", False)
    total_sales = _q2(cash_in + card_in + cash_out + card_out)

    return {
        "date": day.isoformat(),
        "sessions": await list_sessions(session, branch_id=branch_id, day=day),
        "cash_in_session": {"count": cash_in_n, "total": str(cash_in)},
        "card_in_session": {"count": card_in_n, "total": str(card_in)},
        "cash_outside_sessions": {"count": cash_out_n, "total": str(cash_out)},
        "card_outside_sessions": {"count": card_out_n, "total": str(card_out)},
        "invoice_count": cash_in_n + card_in_n + cash_out_n + card_out_n,
        "total_sales": str(total_sales),
    }
