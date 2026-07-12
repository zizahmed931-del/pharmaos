"""Purchasing-domain table mirrors.

P2-M1 adds the full Supplier master. Purchase orders (purchase_orders /
purchase_items) arrive in P2-M2 and will live here too.
"""

from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from pharmaos_api.models.base import Base, MandatoryColumnsMixin


class Supplier(MandatoryColumnsMixin, Base):
    """Supplier master (P2-M1).

    Global (no branch_id) — CLAUDE.md allows suppliers to be shared across
    branches. Extends the Phase-1 name-only table (migration 0900) with full
    management fields (migration 1100). medication_batches.supplier_id FKs here.
    """

    __tablename__ = "suppliers"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tax_registration_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payment_terms: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
