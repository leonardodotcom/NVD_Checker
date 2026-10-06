"""Administration commands.

    python -m app.manage create-user <username>
    python -m app.manage set-password <username>
    python -m app.manage delete-user <username>
    python -m app.manage list-users

Chinese databases (CNNVD / CNVD) need a login session captured by a human:

    python -m app.manage cn-login <cnnvd|cnvd> [--out FILE] [--url URL] [--launch] [--port N]
    python -m app.manage cn-import-session <cnnvd|cnvd> FILE
    python -m app.manage cn-session-status
"""

import argparse
import getpass
import os
import sys

import json
from pathlib import Path

from . import auth
from .db import init_db
from .sources import cn_session


def _ask_password() -> str:
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        sys.exit("Passwords do not match.")
    return password


def _cn_command(args) -> int:
    if args.command == "cn-login":
        from .sources.cn_capture import capture_state

        state = capture_state(args.site, args.url, launch=args.launch, port=args.port)
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(cn_session.validate_state(state), fh)
            print(f"Saved session to {out}. Upload it to the server and run:")
            print(f"    python -m app.manage cn-import-session {args.site} {out.name}")
        else:
            print(f"Saved session to {cn_session.save_state(args.site, state)}")
        print("Treat this file like a password: do not email it or commit it.")
    elif args.command == "cn-import-session":
        try:
            state = json.loads(Path(args.file).read_text(encoding="utf-8"))
            print(f"Installed session at {cn_session.save_state(args.site, state)}")
        except (OSError, ValueError) as exc:
            sys.exit(f"Cannot import session: {exc}")
    else:
        for site in cn_session.SITES:
            status, detail = cn_session.describe(site)
            print(f"{site}\t{status}\t{detail}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.manage", description="NVD Checker administration")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-user", "set-password", "delete-user"):
        p = sub.add_parser(name)
        p.add_argument("username")
    sub.add_parser("list-users")

    login = sub.add_parser("cn-login", help="log in to CNNVD/CNVD in a browser window and save the session")
    login.add_argument("site", choices=cn_session.SITES)
    login.add_argument("--out", help="write the session here instead of the server's session directory")
    login.add_argument("--url", help="page to open first (default: the site's home page)")
    login.add_argument("--launch", action="store_true",
                       help="launch a new browser instead of attaching to your own Chrome (anti-bot sites show a blank page)")
    login.add_argument("--port", type=int, default=9222, help="Chrome debugging port for attach mode (default 9222)")
    imp = sub.add_parser("cn-import-session", help="install a session file captured on another machine")
    imp.add_argument("site", choices=cn_session.SITES)
    imp.add_argument("file")
    sub.add_parser("cn-session-status", help="show whether the saved CNNVD/CNVD sessions are usable")
    args = parser.parse_args(argv)

    if args.command in ("cn-login", "cn-import-session", "cn-session-status"):
        return _cn_command(args)

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
