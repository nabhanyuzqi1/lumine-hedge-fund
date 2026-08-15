# Copyright (c) 2026 Lumine. All rights reserved.
"""Rotate bootstrap user passwords to the current Settings values (G-05).

Usage (VPS):
    docker compose -f docker-compose.vps.yml run --rm migrate \
        python -m scripts.rotate_users

Membaca SUPERADMIN_PASSWORD / ADMIN_PASSWORD / TRADER_PASSWORD dari env
(Settings), re-hash PBKDF2 dengan salt baru, dan UPDATE baris users yang
sudah ada — berbeda dengan seed startup yang hanya INSERT saat user belum
ada. Idempotent; aman dijalankan berulang.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from lumine.api.routers.auth import hash_password, new_salt
from lumine.data.models import User
from lumine.data.session import get_sessionmaker
from lumine.shared.config import get_settings

_BOOTSTRAP: tuple[tuple[str, str, str], ...] = (
    ("superadmin", "superadmin", "superadmin_password"),
    ("admin", "admin", "admin_password"),
    ("trader", "user", "trader_password"),
)


async def main() -> int:
    settings = get_settings()
    updated = 0
    async with get_sessionmaker()() as session:
        for name, role, field in _BOOTSTRAP:
            password = getattr(settings, field)
            row = await session.execute(select(User).where(User.username == name))
            user = row.scalar_one_or_none()
            if user is None:
                print(f"skip {name}: user belum ada (seed dulu via startup api)")
                continue
            salt = new_salt()
            user.password_hash = hash_password(password, salt)
            user.password_salt = salt
            user.role = role
            updated += 1
            print(f"rotated {name} (role={role})")
        await session.commit()
    print(f"done: {updated} user(s) rotated")
    return 0 if updated else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
