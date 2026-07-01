"""CLI: создать super_admin.

Запуск: python -m scripts.seed_admin --username root --password <pwd>
"""
import argparse
import asyncio

from src.database import async_session, init_db
from src.services.auth import hash_password
from src.models.admin_user import AdminUser, AdminRole


async def _run(args):
    await init_db()
    async with async_session() as session:
        session.add(AdminUser(
            username=args.username,
            password_hash=hash_password(args.password),
            role=AdminRole.SUPER_ADMIN,
            studio_id=None,
        ))
        await session.commit()
    print(f"super_admin '{args.username}' создан")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
