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
