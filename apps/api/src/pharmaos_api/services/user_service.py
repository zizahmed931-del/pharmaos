"""User service — the service-layer boundary for the encrypted phone field.

CLAUDE.md: encryption happens here, before write; decryption only on
authorized reads. Phase 1's user-management UI consumes these functions.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from pharmaos_api.models import User
from pharmaos_api.security.crypto import decrypt_field, encrypt_field

_PHONE_CONTEXT = "users.phone"


async def set_user_phone(session: AsyncSession, user: User, phone: str | None) -> None:
    """Store the user's phone encrypted (or clear it)."""
    user.phone_encrypted = (
        encrypt_field(phone, context=_PHONE_CONTEXT) if phone is not None else None
    )
    await session.commit()


def get_user_phone(user: User) -> str | None:
    """Decrypt the user's phone for an AUTHORIZED read path."""
    if user.phone_encrypted is None:
        return None
    return decrypt_field(bytes(user.phone_encrypted), context=_PHONE_CONTEXT)
