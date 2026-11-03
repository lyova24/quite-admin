"""Bounded, non-sensitive field snapshots for persistent activity history only.

These values must never be forwarded to diagnostic/application loggers.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .concurrency import canonical
from .config import is_sensitive_field

MAX_VALUE_BYTES = 4096
MAX_DETAILS_BYTES = 512 * 1024
MAX_CHANGES = 200
HistoryLevel = Literal["changes", "audit", "all"]
WRITE_ACTIONS = frozenset({"create", "edit", "inline_edit", "delete"})


def validate_history_level(level):
    if level not in ("changes", "audit", "all"):
        raise ValueError("history_level must be 'changes', 'audit' or 'all'.")
    return level


def activity_allowed(level, action, outcome):
    if level == "all":
        return True
    write = action in WRITE_ACTIONS or action.startswith("action:")
    if level == "changes":
        return write and outcome == "success"
    return write or action in {"login", "logout", "export"}


def sensitive_name(name):
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(name))
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", normalized)
    normalized = re.sub(r"[-.\s]+", "_", normalized).casefold()
    return (
        is_sensitive_field(normalized)
        or bool(
            set(normalized.split("_"))
            & {"token", "secret", "credential", "credentials", "password"}
        )
        or normalized in {"jwt", "private_key", "api_key", "session_key", "access_key"}
    )


@dataclass(frozen=True)
class FieldChange:
    name: str
    label: str
    before: str | None
    after: str | None
    kind: str = "string"
    before_present: bool = True
    after_present: bool = True
    before_truncated: bool = False
    after_truncated: bool = False
    target_collection: str = ""


@dataclass(frozen=True)
class ActivityDetails:
    changes: tuple[FieldChange, ...] = ()
    record_key: str = ""
    record_exists: bool = True
    omitted: int = 0


def _safe(value, *, depth=0, budget=None):
    """Redact nested credentials and bound JSON traversal before serializing it."""
    budget = [10000] if budget is None else budget
    budget[0] -= 1
    if depth > 20 or budget[0] < 0:
        return "…", True
    if isinstance(value, Mapping):
        result, truncated = {}, False
        for name, item in value.items():
            if sensitive_name(name):
                result[str(name)] = "[redacted]"
                continue
            result[str(name)], clipped = _safe(item, depth=depth + 1, budget=budget)
            truncated |= clipped
            if budget[0] < 0:
                break
        return result, truncated
    if isinstance(value, (list, tuple)):
        result, truncated = [], False
        for item in value:
            safe, clipped = _safe(item, depth=depth + 1, budget=budget)
            result.append(safe)
            truncated |= clipped
            if budget[0] < 0:
                break
        return result, truncated
    return value, False


def clip_text(text):
    encoded = text.encode("utf-8")
    return encoded[:MAX_VALUE_BYTES].decode("utf-8", errors="ignore"), len(
        encoded
    ) > MAX_VALUE_BYTES


def _text(field, value):
    return (None, False) if value is None else clip_text(field.format(value))


def scalar_changes(schema, options, before, after):
    before = {} if before is None else before
    after = {} if after is None else after
    visible = {field.name for field in options.visible_fields(schema)}
    changes = []
    for field in schema.fields:
        if (
            field.name not in visible
            or sensitive_name(field.name)
            or field.kind in {"binary", "unsupported"}
        ):
            continue
        old_present, new_present = field.name in before, field.name in after
        old, old_clipped = _safe(before.get(field.name))
        new, new_clipped = _safe(after.get(field.name))
        if old_present == new_present and canonical(old) == canonical(new):
            continue
        old_text, old_long = _text(field, old)
        new_text, new_long = _text(field, new)
        changes.append(
            FieldChange(
                name=field.name,
                label=field.label,
                before=old_text,
                after=new_text,
                kind=field.kind,
                before_present=old_present,
                after_present=new_present,
                before_truncated=old_clipped or old_long,
                after_truncated=new_clipped or new_long,
            )
        )
    return changes


def safe_record_key(schema, options, record):
    visible = {field.name for field in options.visible_fields(schema)}
    if record and all(
        field.name in visible and not sensitive_name(field.name) and field.name in record
        for field in schema.primary_keys
    ):
        key = schema.record_key(dict(record))
        return key if len(key) <= 8192 else ""
    return ""


def encode_details(details):
    from dataclasses import asdict

    return json.dumps(asdict(details), ensure_ascii=False, allow_nan=False)


def decode_details(payload):
    data = json.loads(payload)
    return ActivityDetails(
        changes=tuple(FieldChange(**change) for change in data.get("changes", ())),
        record_key=data.get("record_key", ""),
        record_exists=data.get("record_exists", True),
        omitted=data.get("omitted", 0),
    )


def bounded_details(changes, *, record_key="", record_exists=True):
    selected = []
    size = len(record_key.encode()) + 1024
    for change in changes:
        encoded = encode_details(ActivityDetails(changes=(change,)))
        size += len(encoded.encode())
        if len(selected) == MAX_CHANGES or size > MAX_DETAILS_BYTES:
            break
        selected.append(change)
    return ActivityDetails(tuple(selected), record_key, record_exists, len(changes) - len(selected))
