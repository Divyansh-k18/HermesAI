"""Inventory: the stock an organization holds, which the Check stock step reads."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.inventory import add_sample_stock
from app.models import InventoryItem

router = APIRouter(prefix="/api/v1/orgs/{org_id}/inventory", tags=["inventory"])

MAX_ITEMS = 1000


class ItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=64)
    quantity: int = Field(ge=0, le=1_000_000_000)
    unit: str = Field(default="unit", min_length=1, max_length=30)
    unit_price: float | None = Field(default=None, ge=0, le=1_000_000_000)


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    sku: str | None = Field(default=None, max_length=64)
    quantity: int | None = Field(default=None, ge=0, le=1_000_000_000)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    unit_price: float | None = Field(default=None, ge=0, le=1_000_000_000)


class ItemOut(BaseModel):
    id: str
    name: str
    sku: str | None
    quantity: int
    unit: str
    unit_price: float | None
    updated_at: datetime


def _out(item: InventoryItem) -> ItemOut:
    return ItemOut(
        id=item.id,
        name=item.name,
        sku=item.sku,
        quantity=item.quantity,
        unit=item.unit,
        unit_price=item.unit_price,
        updated_at=item.updated_at,
    )


def _item(db: Session, org_id: str, item_id: str) -> InventoryItem:
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.organization_id == org_id))
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found.")
    return item


def _audit(db: Session, request: Request, access: OrgAccess, action: str, item: InventoryItem) -> None:
    record_audit(
        db,
        action=action,
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="inventory_item",
        target_id=item.id,
        metadata={"name": item.name, "quantity": item.quantity},
        trace_id=trace_id_of(request),
    )


def _save(db: Session) -> None:
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An item with this name already exists.") from None


@router.get("", response_model=list[ItemOut])
def list_items(
    access: OrgAccess = Depends(org_access("inventory:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[ItemOut]:
    rows = db.scalars(
        select(InventoryItem).where(InventoryItem.organization_id == access.org_id).order_by(InventoryItem.name)
    ).all()
    return [_out(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ItemOut)
def create_item(
    payload: ItemIn,
    request: Request,
    access: OrgAccess = Depends(org_access("inventory:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> ItemOut:
    count = len(db.scalars(select(InventoryItem.id).where(InventoryItem.organization_id == access.org_id)).all())
    if count >= MAX_ITEMS:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=f"An organization can hold up to {MAX_ITEMS} items.")
    item = InventoryItem(
        organization_id=access.org_id,
        name=payload.name.strip(),
        sku=(payload.sku or "").strip() or None,
        quantity=payload.quantity,
        unit=payload.unit.strip(),
        unit_price=payload.unit_price,
    )
    db.add(item)
    _save(db)
    _audit(db, request, access, "inventory.create", item)
    db.commit()
    return _out(item)


@router.post("/sample", response_model=list[ItemOut])
def add_samples(
    request: Request,
    access: OrgAccess = Depends(org_access("inventory:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> list[ItemOut]:
    """Fill in demo stock. Only adds items that are missing, so it is safe to press twice."""
    added = add_sample_stock(db, access.org_id)
    record_audit(
        db,
        action="inventory.sample",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="inventory_item",
        target_id=None,
        metadata={"added": added},
        trace_id=trace_id_of(request),
    )
    db.commit()
    rows = db.scalars(
        select(InventoryItem).where(InventoryItem.organization_id == access.org_id).order_by(InventoryItem.name)
    ).all()
    return [_out(row) for row in rows]


@router.patch("/{item_id}", response_model=ItemOut)
def update_item(
    item_id: str,
    payload: ItemPatch,
    request: Request,
    access: OrgAccess = Depends(org_access("inventory:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> ItemOut:
    item = _item(db, access.org_id, item_id)
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if key in {"name", "unit"} and value is not None:
            value = value.strip()
        if key == "sku":
            value = (value or "").strip() or None
        if value is None and key in {"name", "quantity", "unit"}:
            continue
        setattr(item, key, value)
    _save(db)
    _audit(db, request, access, "inventory.update", item)
    db.commit()
    return _out(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("inventory:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    item = _item(db, access.org_id, item_id)
    _audit(db, request, access, "inventory.delete", item)
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
