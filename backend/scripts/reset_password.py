"""Set a new password for an account in the local database (there is no email recovery yet).

Usage (from the backend folder):
    .venv\\Scripts\\python scripts\\reset_password.py you@example.com

The new password is typed twice and not shown on screen. It must follow the normal rules (at least 12
characters, upper and lower case letters, and a digit). Every signed-in session of that account is ended.
This changes the database on this machine only. Anyone who can run it can already read that database.
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select, update  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.models import AuthSession, User, utcnow  # noqa: E402
from app.security import hash_password, password_policy_errors  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    email = sys.argv[1].strip().lower()
    session_factory = make_session_factory(make_engine(get_settings().database_url))
    with session_factory() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            print(f"No account with the email {email} on this machine.")
            return 1
        for _ in range(3):
            password = getpass.getpass("New password: ")
            problems = password_policy_errors(password)
            if problems:
                print(" ".join(problems))
                continue
            if getpass.getpass("Type it again: ") != password:
                print("The two passwords do not match.")
                continue
            break
        else:
            print("Password not changed.")
            return 1
        user.password_hash = hash_password(password)
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        db.commit()
    print(f"Password changed for {email}. Sign in with the new password.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
