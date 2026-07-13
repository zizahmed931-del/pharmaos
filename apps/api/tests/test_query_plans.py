"""Query-plan guards for the latency-critical hot paths.

CLAUDE.md sets hard latency targets (barcode scan -> display < 50ms, search
< 100ms). Those are verified END-TO-END on the target device
(docs/pilot-checklist.md) — a wall-clock assert on a shared, CPU-throttled CI
runner is flaky and meaningless (it measured latency, not correctness, and
produced false failures).

Instead we guard the STRUCTURAL guarantee that actually delivers those targets,
deterministically: each hot query MUST be served by its index, never a
sequential scan. Technique: `SET LOCAL enable_seqscan = off` makes the planner
reveal the index-backed path it would choose; we assert the expected index
appears in the EXPLAIN output. This is dataset-size- and machine-independent,
so it catches a dropped-index / seq-scan regression without ever flaking on
timing. (Matches CLAUDE.md's "EXPLAIN ANALYZE any query > 50ms" guidance.)
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _plan(db_session: AsyncSession, explain_sql: str) -> str:
    """Return the EXPLAIN plan text with sequential scans disabled, so the
    planner exposes the index path the hot query relies on."""
    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    rows = (await db_session.execute(text(explain_sql))).scalars().all()
    return "\n".join(rows)


async def test_barcode_lookup_is_index_backed(db_session: AsyncSession) -> None:
    """POS scan resolves by exact barcode (sales_service.resolve_barcode) —
    must hit idx_barcodes_barcode (delivers the < 50ms scan target)."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM medication_barcodes WHERE barcode = 'EXPLAIN-PROBE-123'",
    )
    assert "idx_barcodes_barcode" in plan, plan


async def test_arabic_fts_search_is_index_backed(db_session: AsyncSession) -> None:
    """Arabic FTS search (catalog_service.list_medications) must hit the GIN
    search_vector index idx_medications_fts (delivers the < 100ms search target)."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM medications WHERE NOT is_deleted "
        "AND search_vector @@ plainto_tsquery('arabic_simple', normalize_arabic('كونجيستال'))",
    )
    assert "idx_medications_fts" in plan, plan


async def test_arabic_trigram_fallback_is_index_backed(db_session: AsyncSession) -> None:
    """The trigram typo/partial fallback must hit the normalized-name GIN index
    idx_medications_trgm."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM medications "
        "WHERE normalize_arabic(trade_name_ar) % normalize_arabic('كونجستال')",
    )
    assert "idx_medications_trgm" in plan, plan


async def test_expiry_alert_scan_is_index_backed(db_session: AsyncSession) -> None:
    """P2-M4 expiry alerts scan a branch's ACTIVE batches by expiry horizon —
    must hit the partial idx_batches_expiry (branch_id, expiry_date) index."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT b.id FROM medication_batches b "
        "WHERE b.branch_id = '00000000-0000-0000-0000-000000000001' "
        "AND b.status = 'active' AND b.quantity > 0 "
        "AND b.expiry_date <= CURRENT_DATE + 90",
    )
    assert "idx_batches_expiry" in plan, plan


async def test_batch_status_report_is_index_backed(db_session: AsyncSession) -> None:
    """P2-M4 batch reports filter a branch's batches by a selective (non-active)
    status — must hit idx_batches_branch_status (branch_id, status)."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM medication_batches "
        "WHERE branch_id = '00000000-0000-0000-0000-000000000001' "
        "AND status = 'quarantined' AND NOT is_deleted",
    )
    assert "idx_batches_branch_status" in plan, plan


async def test_customer_name_search_is_index_backed(db_session: AsyncSession) -> None:
    """P2-M5 customer lookup by Arabic name (trigram) must hit the normalized-name
    GIN index idx_customers_name_trgm."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM customers "
        "WHERE normalize_arabic(name) % normalize_arabic('محمد')",
    )
    assert "idx_customers_name_trgm" in plan, plan


async def test_controlled_substance_log_medication_scan_is_index_backed(
    db_session: AsyncSession,
) -> None:
    """P2-M8 — a pharmacist looking up one controlled drug's dispensing history
    must hit idx_controlled_log_medication (medication_id, created_at DESC)."""
    plan = await _plan(
        db_session,
        "EXPLAIN SELECT id FROM controlled_substance_log "
        "WHERE medication_id = '00000000-0000-0000-0000-000000000001' "
        "ORDER BY created_at DESC",
    )
    assert "idx_controlled_log_medication" in plan, plan
