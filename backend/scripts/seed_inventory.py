"""Add the sample office-supply stock to organizations in the local database.

Usage (from the backend folder):
    .venv\\Scripts\\python scripts\\seed_inventory.py            # every organization
    .venv\\Scripts\\python scripts\\seed_inventory.py "Acme"     # organizations whose name contains "Acme"

Only items an organization does not have yet are added; existing items and their counts are left alone.
The same data is behind the "Add sample stock" button on the Inventory page.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import make_engine, make_session_factory  # noqa: E402
from app.inventory import add_sample_stock  # noqa: E402
from app.models import Organization  # noqa: E402


def main() -> int:
    name_filter = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    session_factory = make_session_factory(make_engine(get_settings().database_url))
    with session_factory() as db:
        orgs = [org for org in db.scalars(select(Organization)).all() if name_filter in org.name.lower()]
        if not orgs:
            print("No matching organizations. Sign up and create one in Hermes first.")
            return 1
        for org in orgs:
            added = add_sample_stock(db, org.id)
            print(f"{org.name}: added {added} item(s)")
        db.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
