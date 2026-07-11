"""POS endpoints — walking-skeleton slice (scan + sale).

Every endpoint carries a permission dependency (CLAUDE.md mandatory rule).
The full POS UI (shortcuts, unit switching, mouse-free flow) is Phase 1.
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
from pharmaos_api.services import sales_service

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])


@router.get("/scan")
async def scan(
    barcode: str = Query(min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_permission("inventory.view")),
) -> dict[str, object]:
    """Exact barcode lookup — the fastest POS path (target < 50ms)."""
    result = await sales_service.resolve_barcode(session, barcode)
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
        }
    )


class SaleLineIn(BaseModel):
    barcode: str = Field(min_length=1, max_length=64)
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
        lines=[sales_service.SaleLine(barcode=x.barcode, quantity=x.quantity) for x in body.lines],
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
