"""Stock checks: compare the lines of an order with the organization's inventory.

Matching is deterministic. Names are compared by their words, ignoring case, plurals, and packaging words
such as "box" or "pack", so "50 boxes of A4 paper" matches an item called "A4 Paper". An order line that
matches nothing, or whose quantity is unknown, is never treated as available: a person checks it.
"""

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InventoryItem

_WORD = re.compile(r"[a-z0-9]+")
# Packaging and filler words say how an item is sold, not what it is.
_IGNORED = frozenset(
    {"of", "the", "a", "an", "and", "box", "boxes", "pack", "packs", "packet", "packets", "pcs", "piece", "pieces"}
    | {"unit", "units", "nos", "no", "carton", "cartons", "set", "sets", "pair", "pairs", "ream", "reams"}
)
MIN_MATCH = 0.5

# Office supplies for demos. A4 Paper and Blue Pen match the sample order email (50 boxes and 20 packs come to
# exactly ₹78,000). Some items are low or out of stock so the stock-problem path can be shown.
SAMPLE_STOCK: tuple[dict[str, Any], ...] = (
    {"name": "A4 Paper", "sku": "PAP-A4", "quantity": 200, "unit": "box", "unit_price": 1200},
    {"name": "Blue Pen", "sku": "PEN-BLU", "quantity": 100, "unit": "pack", "unit_price": 900},
    {"name": "Black Pen", "sku": "PEN-BLK", "quantity": 80, "unit": "pack", "unit_price": 900},
    {"name": "Whiteboard Marker", "sku": "MRK-WB", "quantity": 8, "unit": "pack", "unit_price": 450},
    {"name": "Sticky Notes", "sku": "NOTE-STK", "quantity": 60, "unit": "pack", "unit_price": 120},
    {"name": "Spiral Notebook", "sku": "NB-SPR", "quantity": 120, "unit": "piece", "unit_price": 85},
    {"name": "File Folder", "sku": "FLD-01", "quantity": 300, "unit": "piece", "unit_price": 25},
    {"name": "Stapler", "sku": "STP-01", "quantity": 5, "unit": "piece", "unit_price": 350},
    {"name": "Staple Pins", "sku": "STP-PIN", "quantity": 150, "unit": "box", "unit_price": 40},
    {"name": "Calculator", "sku": "CALC-12", "quantity": 12, "unit": "piece", "unit_price": 750},
    {"name": "Envelope", "sku": "ENV-A4", "quantity": 40, "unit": "pack", "unit_price": 300},
    {"name": "Printer Ink", "sku": "INK-BLK", "quantity": 0, "unit": "cartridge", "unit_price": 2500},
)


def add_sample_stock(db: Session, organization_id: str) -> int:
    """Add the sample items an organization does not have yet. Existing items, and their counts, are left alone."""
    existing = {
        name.lower()
        for name in db.scalars(select(InventoryItem.name).where(InventoryItem.organization_id == organization_id))
    }
    added = 0
    for sample in SAMPLE_STOCK:
        if sample["name"].lower() not in existing:
            db.add(InventoryItem(organization_id=organization_id, **sample))
            added += 1
    db.flush()
    return added


def _words(name: str) -> set[str]:
    words = set()
    for word in _WORD.findall(name.lower()):
        if word in _IGNORED:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        words.add(word)
    return words


def best_match(name: str, items: list[InventoryItem]) -> InventoryItem | None:
    wanted = _words(name)
    if not wanted:
        return None
    best, best_score = None, 0.0
    for item in items:
        name_words = _words(item.name)
        if not name_words:
            continue
        have = name_words | ({item.sku.lower()} if item.sku else set())
        # Share of words in common, against the longer of the two names, so "paper" alone half-matches "A4 paper".
        score = len(wanted & have) / max(len(wanted), len(name_words))
        if score > best_score:
            best, best_score = item, score
    return best if best_score >= MIN_MATCH else None


def _quantity(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value >= 0 else None


def check_stock(db: Session, organization_id: str, lines: list[Any]) -> dict[str, Any]:
    items = list(db.scalars(select(InventoryItem).where(InventoryItem.organization_id == organization_id)).all())
    checked = []
    for line in lines[:50]:
        name = str(line.get("name") or "").strip() if isinstance(line, dict) else ""
        requested = _quantity(line.get("quantity")) if isinstance(line, dict) else None
        match = best_match(name, items) if name else None
        if match is None:
            state = "not_stocked"
        elif requested is None:
            state = "quantity_unknown"
        elif match.quantity >= requested:
            state = "available"
        else:
            state = "short"
        checked.append(
            {
                "item": name[:200],
                "requested": requested,
                "matched": match.name if match else None,
                "available": match.quantity if match else 0,
                "unit": match.unit if match else None,
                "status": state,
            }
        )
    all_available = bool(checked) and all(line["status"] == "available" for line in checked)
    if all_available:
        status = "in_stock"
    elif any(line["status"] in {"short", "not_stocked"} for line in checked):
        status = "short"
    else:
        status = "needs_check"
    return {
        "status": status,
        "all_available": all_available,
        "lines": checked,
        "problems": [
            f"{line['item']}: {line['status'].replace('_', ' ')}" for line in checked if line["status"] != "available"
        ],
    }
