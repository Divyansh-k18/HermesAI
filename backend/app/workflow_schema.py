"""Workflow definition schema.

A definition is a directed graph of typed nodes. This module only checks that a document is
well-formed and bounded. Whether a graph is complete and publishable is decided by
app/workflow_validation.py.
"""

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NodeType = Literal[
    "trigger",
    "ai_agent",
    "condition",
    "transformation",
    "crm",
    "erp",
    "database",
    "email",
    "http",
    "inventory",
    "approval",
    "delay",
    "end",
]

NODE_TYPES: tuple[str, ...] = (
    "trigger",
    "ai_agent",
    "condition",
    "transformation",
    "crm",
    "erp",
    "database",
    "email",
    "http",
    "inventory",
    "approval",
    "delay",
    "end",
)

MAX_NODES = 200
MAX_EDGES = 400
MAX_NODE_CONFIG_BYTES = 20_000
MAX_DEFINITION_BYTES = 512_000
_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=-100_000, le=100_000)
    y: float = Field(ge=-100_000, le=100_000)


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID_PATTERN)
    type: NodeType
    label: str = Field(default="", max_length=120)
    position: Position
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _bounded_config(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value, default=str)) > MAX_NODE_CONFIG_BYTES:
            raise ValueError("Node configuration is too large.")
        return value


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID_PATTERN)
    source: str = Field(pattern=_ID_PATTERN)
    target: str = Field(pattern=_ID_PATTERN)
    # Named output of the source node: "true"/"false" for conditions, "approved"/"rejected" for approvals.
    source_handle: str | None = Field(default=None, max_length=32)
    label: str = Field(default="", max_length=120)


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[Node] = Field(default_factory=list, max_length=MAX_NODES)
    edges: list[Edge] = Field(default_factory=list, max_length=MAX_EDGES)

    @model_validator(mode="after")
    def _bounded_document(self) -> "Definition":
        if len(self.model_dump_json()) > MAX_DEFINITION_BYTES:
            raise ValueError("Workflow definition is too large.")
        return self


EMPTY_DEFINITION: dict[str, list] = {"nodes": [], "edges": []}
