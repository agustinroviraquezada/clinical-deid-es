"""Print the argon2 hash of the demo password for DEMO_PASSWORD_HASH (T4.2, design §7).

The password is read without echo and never written anywhere. Usage:
    uv run python scripts/hash_password.py
"""

import getpass
import sys

from argon2 import PasswordHasher


def main() -> int:
    password = getpass.getpass("Demo password: ")
    if len(password) < 12:
        print("Use at least 12 characters.", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat it: ") != password:
        print("The passwords do not match.", file=sys.stderr)
        return 1
    print(PasswordHasher().hash(password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
