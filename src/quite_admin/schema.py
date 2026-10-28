from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, get_origin
from uuid import UUID

from .errors import NotFound
from .i18n import Message


def kind_for(python_type: type) -> str:
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return "enum"
    return {
        str: "string",
        int: "integer",
        float: "number",
        Decimal: "number",
        bool: "boolean",
        dict: "json",
        list: "json",
        datetime: "datetime",
        date: "date",
        time: "time",
        UUID: "uuid",
        bytes: "binary",
    }.get(get_origin(python_type) or python_type, "unsupported")


@dataclass(frozen=True)
class Field:
    name: str
    python_type: type = str
    label: str | None = None
    kind: str | None = None
    nullable: bool = False
    primary_key: bool = False
    generated: bool = False
    read_only: bool = False
    has_default: bool = False
    max_length: int | None = None
    choices: tuple[str, ...] = ()
    foreign_key: str | None = None

    def __post_init__(self) -> None:
        if not self.name or self.name.startswith("__"):
            raise ValueError("Field names must be nonempty and cannot start with '__'.")
        object.__setattr__(self, "kind", self.kind or kind_for(self.python_type))
        object.__setattr__(self, "label", self.label or self.name.replace("_", " ").title())
        if self.kind in {"unsupported", "binary"}:
            object.__setattr__(self, "read_only", True)
        if self.kind == "enum" and not self.choices:
            values = tuple(str(item.value) for item in self.python_type)
            object.__setattr__(self, "choices", values)

    def parse(self, value: Any) -> Any:
        if value is None or (value == "" and self.nullable):
            if not self.nullable:
                raise ValueError(Message("A value is required."))
            return None
        raw = str(value)
        try:
            if self.kind == "boolean":
                if raw.lower() not in {"true", "false", "1", "0"}:
                    raise ValueError(Message("Choose true or false."))
                result = raw.lower() in {"true", "1"}
            elif self.kind == "json":
                result = json.loads(raw)
                if result is None:
                    if not self.nullable:
                        raise ValueError(Message("A value is required."))
                elif self.python_type in {dict, list} and not isinstance(result, self.python_type):
                    raise ValueError(
                        Message("Expected a JSON {type}.", type=self.python_type.__name__)
                    )
                # Reject NaN / Infinity, including in nested JSON values.
                json.dumps(result, allow_nan=False)
            elif self.kind in {"datetime", "date", "time"}:
                result = self.python_type.fromisoformat(raw)
            elif self.kind == "enum":
                result = next(item for item in self.python_type if str(item.value) == raw)
            else:
                result = self.python_type(raw)
                if isinstance(result, (float, Decimal)) and not math.isfinite(result):
                    raise ValueError(Message("Enter a finite number."))
            if self.kind != "enum" and self.max_length is not None and len(raw) > self.max_length:
                raise ValueError(Message("Use at most {count} characters.", count=self.max_length))
            if self.choices and raw not in self.choices:
                raise ValueError(Message("Choose one of the available values."))
            return result
        except (ValueError, TypeError, InvalidOperation, StopIteration, OverflowError) as exc:
            if exc.args and isinstance(exc.args[0], Message):
                raise
            raise ValueError(Message("Enter a valid {kind}.", kind=self.kind)) from exc

    def format(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, Enum):
            return str(value.value)
        if self.kind == "json":
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        if isinstance(value, (datetime, date, time)):
            return value.isoformat()
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)


@dataclass(frozen=True)
class ModelSchema:
    name: str
    fields: tuple[Field, ...]
    label: str | None = None

    def __post_init__(self) -> None:
        if len({field.name for field in self.fields}) != len(self.fields):
            raise ValueError("Duplicate field names.")
        if not self.primary_keys:
            raise ValueError(f"{self.name} has no primary key; records cannot be addressed safely.")
        object.__setattr__(self, "label", self.label or self.name.replace("_", " ").title())

    @property
    def primary_keys(self) -> tuple[Field, ...]:
        return tuple(field for field in self.fields if field.primary_key)

    @property
    def by_name(self) -> dict[str, Field]:
        return {field.name: field for field in self.fields}

    def record_key(self, record: dict[str, Any]) -> str:
        # One URL-safe format for string, UUID and composite identities, including slashes.
        values = [field.format(record[field.name]) for field in self.primary_keys]
        raw = json.dumps(values, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def parse_key(self, token: str) -> dict[str, Any]:
        try:
            if len(token) > 8192:
                raise ValueError("Key too long")
            values = json.loads(
                base64.b64decode(token + "=" * (-len(token) % 4), altchars=b"-_", validate=True)
            )
            if not isinstance(values, list) or len(values) != len(self.primary_keys):
                raise ValueError("Invalid key")
            if any(not isinstance(value, str) for value in values):
                raise ValueError("Invalid key")
            return {
                field.name: field.parse(value)
                for field, value in zip(self.primary_keys, values, strict=True)
            }
        except (ValueError, TypeError, KeyError) as exc:
            raise NotFound("Record not found.") from exc


@dataclass(frozen=True)
class Query:
    offset: int = 0
    limit: int = 25
    search: str = ""
    search_fields: tuple[str, ...] = ()
    order_by: str | None = None
    descending: bool = False


@dataclass(frozen=True)
class RecordPage:
    records: list[dict[str, Any]]
    total: int
