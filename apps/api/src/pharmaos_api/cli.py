"""Operational CLI.

bootstrap-admin: create the first super_admin user (Phase 0 acceptance:
"clean copy -> docker compose up -> migrate -> super_admin login").

The super_admin ROLE row is upserted here by code (the same code-defined
role the M7 seeder maintains) — never created by hand in the DB.
Credentials come from arguments/environment — never hardcoded (forbidden #4).

backup create / backup restore-drill / backup export-key: operational entry
points for the encrypted-backup subsystem (M9). export-key prints the backup
key ONCE for the owner to store OFFLINE — it is the recovery root.

Usage:
    python -m pharmaos_api.cli bootstrap-admin --username <name> --full-name <name>
    (password via PHARMAOS_ADMIN_PASSWORD env var or interactive prompt)
    python -m pharmaos_api.cli backup create [--backup-dir PATH] [--no-cloud]
    python -m pharmaos_api.cli backup restore-drill --file PATH --drill-database-url URL
    python -m pharmaos_api.cli backup export-key
"""

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

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


def _backup_create(backup_dir: Path, *, cloud: bool) -> int:
    from pharmaos_api.services import backup_service

    backup_file = backup_service.create_backup(backup_dir)
    print(f"backup created: {backup_file}")
    if cloud:
        uploaded = backup_service.upload_to_cloud(backup_file)
        print("cloud copy: uploaded" if uploaded else "cloud copy: skipped (not configured)")
    return 0


def _backup_restore_drill(backup_file: Path, drill_database_url: str) -> int:
    from pharmaos_api.services import backup_service

    counts = backup_service.restore_drill(backup_file, drill_database_url=drill_database_url)
    print(f"restore drill OK: {counts}")
    return 0


def _backup_export_key() -> int:
    from pharmaos_api.security import keystore

    print(keystore.ensure_backup_key().hex())
    print(
        "⚠️  Store this backup key OFFLINE (paper/sealed envelope). "
        "Without it, backups cannot be restored after device loss.",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pharmaos-api")
    sub = parser.add_subparsers(dest="command", required=True)

    boot = sub.add_parser("bootstrap-admin", help="Create the first super_admin user.")
    boot.add_argument("--username", required=True)
    boot.add_argument("--full-name", required=True)

    backup = sub.add_parser("backup", help="Encrypted backup operations.")
    backup_sub = backup.add_subparsers(dest="backup_command", required=True)
    b_create = backup_sub.add_parser("create", help="Create an encrypted backup now.")
    b_create.add_argument("--backup-dir", default=os.environ.get("BACKUP_PATH", "./backups"))
    b_create.add_argument("--no-cloud", action="store_true")
    b_drill = backup_sub.add_parser("restore-drill", help="Restore into a scratch DB and verify.")
    b_drill.add_argument("--file", required=True)
    b_drill.add_argument("--drill-database-url", required=True)
    backup_sub.add_parser("export-key", help="Print the backup key for OFFLINE safekeeping.")

    args = parser.parse_args(argv)
    if args.command == "bootstrap-admin":
        password = os.environ.get("PHARMAOS_ADMIN_PASSWORD") or getpass.getpass(
            "super_admin password: "
        )
        return asyncio.run(_bootstrap_admin(args.username, args.full_name, password))
    if args.command == "backup":
        if args.backup_command == "create":
            return _backup_create(Path(args.backup_dir), cloud=not args.no_cloud)
        if args.backup_command == "restore-drill":
            return _backup_restore_drill(Path(args.file), args.drill_database_url)
        if args.backup_command == "export-key":
            return _backup_export_key()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
