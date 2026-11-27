"""CLI: python -m app.cli <command>"""
from __future__ import annotations

import argparse
import asyncio
import secrets
import sys

from . import auth, db


async def cmd_create_user(args) -> None:
    await db.init_pool()
    password = args.password or secrets.token_urlsafe(12)
    async with db.pool().connection() as conn:
        user_id = await auth.create_user(conn, args.username, password)
    print(f"created user {args.username} (id={user_id})")
    if not args.password:
        print(f"password: {password}")
    await db.close_pool()


async def cmd_set_setting(args) -> None:
    import json

    await db.init_pool()
    value = json.loads(args.value)
    await db.set_setting(args.key, value)
    print(f"set {args.key} = {value}")
    await db.close_pool()


async def cmd_show_token(args) -> None:
    await db.init_pool()
    settings = await db.get_settings()
    print(settings.get("bridge_token", ""))
    await db.close_pool()


def main() -> None:
    parser = argparse.ArgumentParser(prog="fund2-cli")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("create-user")
    p.add_argument("username")
    p.add_argument("password", nargs="?", default=None)
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("set-setting")
    p.add_argument("key")
    p.add_argument("value", help="JSON value")
    p.set_defaults(func=cmd_set_setting)

    p = sub.add_parser("show-bridge-token")
    p.set_defaults(func=cmd_show_token)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
