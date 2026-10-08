import argparse
import asyncio
import sys
from collections.abc import Sequence

from aiogram.types import BotCommand

from src.container import Container
from src.infrastructure.config import load_settings

WEBHOOK_PATH = "/api/telegram/webhook"
BOT_COMMANDS = (
    BotCommand(command="list", description="Show your filters"),
    BotCommand(command="add", description="Add a filter by OLX link"),
    BotCommand(command="delete", description="Delete a filter by number"),
    BotCommand(command="help", description="How the bot works"),
)


def _write(line: str) -> None:
    sys.stdout.write(f"{line}\n")


async def _run(arguments: argparse.Namespace) -> int:
    settings = load_settings()
    container = Container(settings)
    try:
        if arguments.command == "set":
            base_url = arguments.url or (
                str(settings.app.public_base_url) if settings.app.public_base_url else None
            )
            if not base_url:
                _write("Provide --url or set APP_PUBLIC_BASE_URL")
                return 2
            target = f"{base_url.rstrip('/')}{WEBHOOK_PATH}"
            await container.bot.set_webhook(
                url=target,
                secret_token=settings.telegram.webhook_secret.get_secret_value(),
                allowed_updates=container.dispatcher.resolve_used_update_types(),
                drop_pending_updates=arguments.drop_pending,
            )
            await container.bot.set_my_commands(list(BOT_COMMANDS))
            _write(f"Webhook set to {target}")
        elif arguments.command == "delete":
            await container.bot.delete_webhook(drop_pending_updates=arguments.drop_pending)
            _write("Webhook deleted")
        else:
            info = await container.bot.get_webhook_info()
            _write(f"url: {info.url or '-'}")
            _write(f"pending updates: {info.pending_update_count}")
            _write(f"last error: {info.last_error_message or '-'}")
    finally:
        await container.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.presentation.cli.webhook")
    commands = parser.add_subparsers(dest="command", required=True)
    set_parser = commands.add_parser("set", help="Register the webhook and bot commands")
    set_parser.add_argument("--url", help="Public base URL, defaults to APP_PUBLIC_BASE_URL")
    set_parser.add_argument("--drop-pending", action="store_true")
    delete_parser = commands.add_parser("delete", help="Remove the webhook")
    delete_parser.add_argument("--drop-pending", action="store_true")
    commands.add_parser("info", help="Show current webhook status")
    return asyncio.run(_run(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
