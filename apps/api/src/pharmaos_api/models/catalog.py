"""Catalog table mirrors (medications / packaging / barcodes) — used by the POS
scan & sale paths. The SQL migrations remain the schema source."""

import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from pharmaos_api.models.base import Base, MandatoryColumnsMixin


class Medication(MandatoryColumnsMixin, Base):
    __tablename__ = "medications"

    trade_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name_ar: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scientific_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    requires_prescription: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    controlled_substance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    eda_registration_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(14), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    # search_vector is a DB-generated column — intentionally not mapped.


class MedicationPackaging(MandatoryColumnsMixin, Base):
    __tablename__ = "medication_packaging"

    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id"), nullable=False
    )
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1=box 2=strip 3=tablet
    unit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(50), nullable=False)
    qty_in_parent: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    is_sellable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("TRUE"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_default_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )


class MedicationBarcode(MandatoryColumnsMixin, Base):
    __tablename__ = "medication_barcodes"

    medication_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medications.id"), nullable=False
    )
    packaging_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("medication_packaging.id"), nullable=True
    )
    barcode: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    barcode_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'EAN13'")
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
