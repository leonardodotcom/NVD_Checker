"""Administration commands.

    python -m app.manage create-user <username>
    python -m app.manage set-password <username>
    python -m app.manage delete-user <username>
    python -m app.manage list-users
"""

import argparse
import getpass
import sys

from . import auth
from .db import init_db


def _ask_password() -> str:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage", description="NVD Checker administration")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-user", "set-password", "delete-user"):
        p = sub.add_parser(name)
        p.add_argument("username")
    sub.add_parser("list-users")
    args = parser.parse_args(argv)

    init_db()
    try:
        if args.command == "create-user":
            auth.create_user(args.username, _ask_password())
            print(f"Created user '{args.username}'.")
        elif args.command == "set-password":
            if not auth.set_password(args.username, _ask_password()):
                sys.exit(f"No such user '{args.username}'.")
            print(f"Password updated for '{args.username}'.")
        elif args.command == "delete-user":
            if not auth.delete_user(args.username):
                sys.exit(f"No such user '{args.username}'.")
            print(f"Deleted user '{args.username}'.")
        elif args.command == "list-users":
            users = auth.list_users()
            for username, created in users:
                print(f"{username}\t{created}")
            if not users:
                print("No users yet. Create one with: python -m app.manage create-user <name>")
    except ValueError as exc:
        sys.exit(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
