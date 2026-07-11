"""POS endpoints (P1-M8: full point of sale).

Every endpoint carries a permission dependency (CLAUDE.md mandatory rule).
- /scan resolves an exact barcode OR a 2D GS1 DataMatrix (Egyptian packs) and
  returns ALL sellable packaging levels so the UI can switch units locally.
- /sale accepts explicit medication_id + packaging_id per line (unit switching
  and name-search lines) in addition to the plain-barcode skeleton shape.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.db import get_session
from pharmaos_api.deps import get_current_user, require_permission
from pharmaos_api.errors import success_envelope
from pharmaos_api.models import InvoiceItem, User
from pharmaos_api.security.csrf import enforce_csrf
from pharmaos_api.services import catalog_service, sales_service

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


@router.get("/scan")
async def scan(
    barcode: str = Query(min_length=1, max_length=120),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_permission("inventory.view")),
) -> dict[str, object]:
    """Barcode / GS1 lookup — the fastest POS path (target < 50ms).

    `levels` carries every sellable packaging level (box/strip/tablet) with its
    price so the cart can switch units without another round-trip.
    """
    result = await sales_service.resolve_scan_code(session, barcode)
    packaging = await catalog_service.get_packaging(session, result.medication_id)
    return success_envelope(
        {
            "medication_id": str(result.medication_id),
            "trade_name": result.trade_name,
            "trade_name_ar": result.trade_name_ar,
            "packaging_id": str(result.packaging_id),
            "packaging_name_ar": result.packaging_name_ar,
            "level": result.level,
            "selling_price": str(result.selling_price),
            "requires_prescription": result.requires_prescription,
            "controlled_substance": result.controlled_substance,
            "levels": [
                {
                    "id": str(p.id),
                    "level": p.level,
                    "name_ar": p.name_ar,
                    "selling_price": str(p.selling_price),
                    "is_default_sale": p.is_default_sale,
                }
                for p in packaging
                if p.is_sellable
            ],
        }
    )


class SaleLineIn(BaseModel):
    """barcode alone, barcode + packaging_id (unit switch), or
    medication_id + packaging_id (name-search line) — validated in the service."""

    barcode: str | None = Field(default=None, min_length=1, max_length=120)
    medication_id: uuid.UUID | None = None
    packaging_id: uuid.UUID | None = None
    quantity: Decimal = Field(gt=0, le=Decimal("100000"))


class SaleIn(BaseModel):
    branch_id: uuid.UUID
    lines: list[SaleLineIn] = Field(min_length=1, max_length=200)
    payment_method: str = Field(default="cash", pattern="^(cash|card)$")


@router.post("/sale")
async def create_sale(
    body: SaleIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("sales.create")),
) -> dict[str, object]:
    """Complete a sale: FEFO batch deduction + movements + invoice, atomically."""
    enforce_csrf(request)
    invoice = await sales_service.create_sale(
        session,
        branch_id=body.branch_id,
        lines=[
            sales_service.SaleLine(
                quantity=x.quantity,
                barcode=x.barcode,
                medication_id=x.medication_id,
                packaging_id=x.packaging_id,
            )
            for x in body.lines
        ],
        cashier=current_user,
        payment_method=body.payment_method,
    )
    items = (
        (await session.execute(select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    return success_envelope(
        {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "currency_code": invoice.currency_code,
            "subtotal": str(invoice.subtotal),
            "total": str(invoice.total),
            "payment_method": invoice.payment_method,
            "items": [
                {
                    "medication_id": str(item.medication_id),
                    "batch_id": str(item.batch_id),
                    "quantity": str(item.quantity),
                    "qty_smallest": str(item.qty_smallest),
                    "line_total": str(item.line_total),
                }
                for item in items
            ],
        }
    )
