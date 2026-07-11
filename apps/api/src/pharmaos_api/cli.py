"""Operational CLI.

bootstrap-admin: create the first super_admin user (Phase 0 acceptance:
"clean copy -> docker compose up -> migrate -> super_admin login").

The super_admin ROLE row is upserted here by code (the same code-defined
role the M7 seeder maintains) — never created by hand in the DB.
Credentials come from arguments/environment — never hardcoded (forbidden #4).

Usage:
    python -m pharmaos_api.cli bootstrap-admin --username <name> --full-name <name>
    (password via PHARMAOS_ADMIN_PASSWORD env var or interactive prompt)
"""

import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from pharmaos_api.db import get_session_factory
from pharmaos_api.models import Role, User
from pharmaos_api.security.passwords import hash_password, validate_password_policy

SUPER_ADMIN_ROLE_CODE = "super_admin"
SUPER_ADMIN_ROLE_NAME_AR = "مالك النظام"


async def _bootstrap_admin(username: str, full_name: str, password: str) -> int:
    violations = validate_password_policy(password)
    if violations:
        print(f"password policy violations: {', '.join(violations)}", file=sys.stderr)
        return 2

    async with get_session_factory()() as session:
        role = (
            await session.execute(select(Role).where(Role.code == SUPER_ADMIN_ROLE_CODE))
        ).scalar_one_or_none()
        if role is None:
            role = Role(
                code=SUPER_ADMIN_ROLE_CODE, name_ar=SUPER_ADMIN_ROLE_NAME_AR, is_system=True
            )
            session.add(role)
            await session.flush()

        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            print(f"user '{username}' already exists — nothing to do.", file=sys.stderr)
            return 1

        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            role_id=role.id,
        )
        session.add(user)
        await session.commit()
        print(f"super_admin '{username}' created.")
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pharmaos-api")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap-admin", help="Create the first super_admin user.")
    boot.add_argument("--username", required=True)
    boot.add_argument("--full-name", required=True)

    args = parser.parse_args(argv)
    if args.command == "bootstrap-admin":
        password = os.environ.get("PHARMAOS_ADMIN_PASSWORD") or getpass.getpass(
            "super_admin password: "
        )
        return asyncio.run(_bootstrap_admin(args.username, args.full_name, password))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
