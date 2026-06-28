"""CLI: создать студию. Запуск: python -m scripts.seed_studio --slug photo28 --name Photo28 --bot-token ... --admin-user owner --admin-pass ..."""
import argparse
import asyncio

from src.database import async_session, init_db
from src.services.studio_provisioning import provision_studio


async def _run(args):
    await init_db()
    async with async_session() as session:
        studio = await provision_studio(
            session,
            slug=args.slug,
            name=args.name,
            bot_token=args.bot_token,
            admin_username=args.admin_user,
            admin_password=args.admin_pass,
        )
    print(f"Создана студия id={studio.id} slug={studio.slug}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--admin-user", required=True)
    parser.add_argument("--admin-pass", required=True)
    asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    main()
