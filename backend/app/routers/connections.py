"""Connections: encrypted credentials that HTTP steps use to call outside APIs.

A connection holds one header (for example Authorization: Bearer ...). The secret is encrypted at rest
and is never returned by any endpoint. Workflows refer to a connection by id, so exporting or viewing a
workflow never exposes a credential.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.crypto import encrypt_secret
from app.deps import OrgAccess, get_db, org_access, trace_id_of
from app.models import Connection

router = APIRouter(prefix="/api/v1/orgs/{org_id}/connections", tags=["connections"])

# RFC 7230 header token characters.
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,100}$")
# Headers a connection must not set, because they would change how the request is routed or framed.
_FORBIDDEN_HEADERS = frozenset({"host", "content-length", "transfer-encoding", "connection", "idempotency-key"})


class ConnectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    header_name: str = Field(default="Authorization", min_length=1, max_length=100)
    secret: str = Field(min_length=1, max_length=4096)

    @field_validator("header_name")
    @classmethod
    def _valid_header(cls, value: str) -> str:
        value = value.strip()
        if not _HEADER_NAME.match(value) or value.lower() in _FORBIDDEN_HEADERS:
            raise ValueError("Use a valid header name such as Authorization or X-Api-Key.")
        return value

    @field_validator("secret")
    @classmethod
    def _single_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("The secret must be a single line.")
        return value


class ConnectionOut(BaseModel):
    id: str
    name: str
    kind: str
    header_name: str
    created_at: datetime


def _out(connection: Connection) -> ConnectionOut:
    return ConnectionOut(
        id=connection.id,
        name=connection.name,
        kind=connection.kind,
        header_name=connection.header_name,
        created_at=connection.created_at,
    )


@router.get("", response_model=list[ConnectionOut])
def list_connections(
    access: OrgAccess = Depends(org_access("connections:read", csrf=False)),
    db: Session = Depends(get_db),
) -> list[ConnectionOut]:
    rows = db.scalars(
        select(Connection).where(Connection.organization_id == access.org_id).order_by(Connection.name)
    ).all()
    return [_out(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConnectionOut)
def create_connection(
    payload: ConnectionIn,
    request: Request,
    access: OrgAccess = Depends(org_access("connections:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> ConnectionOut:
    connection = Connection(
        organization_id=access.org_id,
        name=payload.name.strip(),
        kind="http_header",
        header_name=payload.header_name,
        secret_ciphertext=encrypt_secret(request.app.state.settings, payload.secret),
        created_by_user_id=access.auth.user.id,
    )
    db.add(connection)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A connection with this name already exists.") from None
    record_audit(
        db,
        action="connection.create",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="connection",
        target_id=connection.id,
        metadata={"name": connection.name, "header": connection.header_name},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return _out(connection)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    connection_id: str,
    request: Request,
    access: OrgAccess = Depends(org_access("connections:manage", csrf=True)),
    db: Session = Depends(get_db),
) -> Response:
    connection = db.scalar(
        select(Connection).where(Connection.id == connection_id, Connection.organization_id == access.org_id)
    )
    if connection is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Connection not found.")
    db.delete(connection)
    record_audit(
        db,
        action="connection.delete",
        organization_id=access.org_id,
        actor_user_id=access.auth.user.id,
        target_type="connection",
        target_id=connection_id,
        metadata={"name": connection.name},
        trace_id=trace_id_of(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
