"""Reference-table mirrors: currencies & countries (natural CHAR keys).

These use natural primary keys (ISO codes) per the Phase 0 DDL, so they do NOT
use MandatoryColumnsMixin (which defines a UUID id).
"""

from sqlalchemy import CHAR, ForeignKey, SmallInteger, String, text
from sqlalchemy.orm import Mapped, mapped_column

from pharmaos_api.models.base import Base


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)  # ISO 4217
    name_ar: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("2")
    )


class Country(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(CHAR(2), primary_key=True)  # ISO 3166-1
    name_ar: Mapped[str] = mapped_column(String(80), nullable=False)
    default_currency: Mapped[str] = mapped_column(
        CHAR(3), ForeignKey("currencies.code"), nullable=False
    )
    calendar: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'gregory'")
    )
