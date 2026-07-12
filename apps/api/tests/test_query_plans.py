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
