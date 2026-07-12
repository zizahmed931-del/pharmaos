"""Purchasing endpoints (P2-M1): full supplier management.

Permission tiers (CLAUDE.md matrix — suppliers live under the purchases module):
  view                 = purchases.view (super_admin, branch_manager, pharmacist)
  create / edit        = purchases.create (super_admin, branch_manager)
Mutations enforce CSRF; lists are paginated (<=100). Purchase orders themselves
(purchase_orders / purchase_items) arrive in P2-M2 and will extend this router.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.db import get_session
from pharmaos_api.deps import get_current_user, require_permission
from pharmaos_api.errors import success_envelope
from pharmaos_api.models import User
from pharmaos_api.security.csrf import enforce_csrf
from pharmaos_api.services import supplier_service as svc

router = APIRouter(prefix="/api/v1", tags=["purchases"])

_view = Depends(require_permission("purchases.view"))
_manage = Depends(require_permission("purchases.create"))


class SupplierCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    tax_registration_no: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class SupplierUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=500)
    tax_registration_no: str | None = Field(default=None, max_length=50)
    payment_terms: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


@router.get("/purchases/suppliers")
async def list_suppliers(
    search: str | None = Query(default=None, max_length=120),
    active_only: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=svc.MAX_PAGE_SIZE),
    session: AsyncSession = Depends(get_session),
    _: None = _view,
) -> dict[str, object]:
    rows, total = await svc.list_suppliers(
        session, search=search, active_only=active_only, skip=skip, limit=limit
    )
    return success_envelope(
        rows, meta={"page": skip // limit + 1, "total": total, "per_page": limit}
    )


@router.get("/purchases/suppliers/{supplier_id}")
async def get_supplier(
    supplier_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _: None = _view,
) -> dict[str, object]:
    return success_envelope(svc.to_dict(await svc.get_supplier(session, supplier_id)))


@router.post("/purchases/suppliers")
async def create_supplier(
    body: SupplierCreateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(get_current_user),
    _: None = _manage,
) -> dict[str, object]:
    enforce_csrf(request)
    supplier = await svc.create_supplier(
        session, actor=actor, **body.model_dump(exclude_unset=True)
    )
    return success_envelope(svc.to_dict(supplier))


@router.patch("/purchases/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: uuid.UUID,
    body: SupplierUpdateIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(get_current_user),
    _: None = _manage,
) -> dict[str, object]:
    enforce_csrf(request)
    supplier = await svc.get_supplier(session, supplier_id)
    supplier = await svc.update_supplier(
        session, actor=actor, supplier=supplier, changes=body.model_dump(exclude_unset=True)
    )
    return success_envelope(svc.to_dict(supplier))
