#!/usr/bin/env python3
"""
generate_hashed_password.py — generate a PBKDF2 password hash for ircbnc config.

Usage:
    python generate_hashed_password.py mypassword
    python generate_hashed_password.py              # interactive prompt
"""
import argparse
import getpass
import sys
import os

# Make project modules importable when run from the repo root.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# The shared package has a circular import via shared.multi_network.  Preload
# the leaf modules we need so the imports below succeed.
import shared.buffer  # noqa: F401
import shared.message  # noqa: F401
import shared.auth  # noqa: F401
from shared.auth import PasswordHasher


def main():
    parser = argparse.ArgumentParser(
        description="Generate a password hash for ircbnc's users config."
    )
    parser.add_argument(
        "password",
        nargs="?",
        help="Password to hash. If omitted, a secure prompt is shown.",
    )
    args = parser.parse_args()

    password = args.password
    if password is None:
        password = getpass.getpass("Enter password: ")
        if not password:
            print("Error: password cannot be empty.", file=sys.stderr)
            sys.exit(1)
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Error: passwords do not match.", file=sys.stderr)
            sys.exit(1)

    hashed = PasswordHasher.hash(password)
    print(hashed)


if __name__ == "__main__":
    main()
