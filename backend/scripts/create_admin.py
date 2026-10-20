# Creates an admin account. This is the only way to make an admin; sign-up on the website only makes recruiters.
# Usage (from backend/, with the venv active):  python scripts/create_admin.py
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db
from app.services.accounts import create_admin


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an admin account")
    parser.add_argument("--name")
    parser.add_argument("--email")
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    args = parser.parse_args()

    name = args.name or input("Admin name: ").strip()
    email = args.email or input("Admin email: ").strip()
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = getpass.getpass("Password (at least 8 characters, not shown): ")
        if getpass.getpass("Type it again: ") != password:
            print("The two passwords do not match.")
            return 1

    init_db()
    with SessionLocal() as db:
        try:
            user = create_admin(db, name, email, password)
        except ValueError as exc:
            print(f"Could not create the admin: {exc}.")
            return 1
    print(f"Admin account created for {user.email}. Log in at http://localhost:8000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
