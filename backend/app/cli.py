"""Officer accounts from the command line: python -m app.cli create-officer|set-password|disable-officer (backend/)."""
import argparse
import getpass
import os
import re
import sys

from sqlalchemy import text

from app.auth import hash_password
from app.db import engine

MIN_PASSWORD = 10


def read_password() -> str:
    """From GEOKITTA_PASSWORD (for scripts) or typed twice at a hidden prompt."""
    password = os.environ.get("GEOKITTA_PASSWORD")
    if password is None:
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            sys.exit("passwords do not match")
    if len(password) < MIN_PASSWORD:
        sys.exit(f"password must be at least {MIN_PASSWORD} characters")
    return password


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    create = sub.add_parser("create-officer")
    create.add_argument("username")
    create.add_argument("--name", required=True, help="full name")
    create.add_argument("--office", default="Survey Office (demo)")
    create.add_argument("--admin", action="store_true")
    sub.add_parser("set-password").add_argument("username")
    sub.add_parser("disable-officer").add_argument("username")
    args = ap.parse_args(argv)

    username = args.username.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_.]{2,49}", username):
        sys.exit("username: 3-50 characters, lowercase letters, digits, dot or underscore, starting with a letter")
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM officers WHERE username = :u"), {"u": username}).first()
        if args.cmd == "create-officer":
            if exists:
                sys.exit(f"{username} already exists; use set-password")
            conn.execute(text("INSERT INTO officers (username, password_hash, full_name, office, is_admin) "
                              "VALUES (:u, :h, :n, :o, :a)"),
                         {"u": username, "h": hash_password(read_password()), "n": args.name, "o": args.office,
                          "a": args.admin})
            print(f"created {'admin ' if args.admin else ''}officer {username}")
        elif not exists:
            sys.exit(f"no officer called {username}")
        elif args.cmd == "set-password":
            conn.execute(text("UPDATE officers SET password_hash = :h, is_active = true WHERE username = :u"),
                         {"u": username, "h": hash_password(read_password())})
            print(f"password changed for {username}")
        else:
            conn.execute(text("UPDATE officers SET is_active = false WHERE username = :u"), {"u": username})
            print(f"{username} can no longer sign in")
    return 0


if __name__ == "__main__":
    sys.exit(main())
