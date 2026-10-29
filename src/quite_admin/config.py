from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from .errors import ValidationError
from .i18n import Message
from .schema import Field, ModelSchema

if TYPE_CHECKING:
    from starlette.requests import Request

    from .auth import Identity
    from .operations import Operation

Action = Literal["list", "view", "create", "edit", "delete"]
Permission = Callable[["Request", "Identity", Action], bool | Awaitable[bool]]

PROTECTED_FIELDS = frozenset(
    {
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
        "is_admin",
        "is_superuser",
        "is_staff",
        "roles",
        "permissions",
    }
)


def is_sensitive_field(name: str) -> bool:
    name = name.casefold().strip("_")
    return (
        "password" in name
        or name
        in {
            "secret",
            "token",
            "credentials",
            "authorization",
            "api_key",
            "private_key",
            "session_key",
        }
        or name.endswith(("_token", "_secret", "_password_hash"))
    )


@dataclass(frozen=True)
class RecordAction:
    slug: str
    label: str
    handler: Callable[[Operation], Mapping[str, Any] | None | Awaitable[Mapping[str, Any] | None]]
    permission: Permission | None = None
    required_permission: Action = "edit"

    def __post_init__(self) -> None:
        import re

        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", self.slug):
            raise ValueError("Action slugs must contain letters, digits, hyphens or underscores.")
        if self.required_permission not in {"list", "view", "create", "edit", "delete"}:
            raise ValueError("Unknown required action permission.")


@dataclass(frozen=True)
class FieldOptions:
    label: str | None = None
    read_only: bool = False
    help_text: str = ""
    kind: str | None = None
    parser: Callable[[Any], Any] | None = None
    formatter: Callable[[Any], str] | None = None
    template: str | None = None


@dataclass(frozen=True)
class ModelOptions:
    slug: str | None = None
    label: str | None = None
    list_fields: tuple[str, ...] | None = None
    edit_fields: tuple[str, ...] | None = None
    create_fields: tuple[str, ...] | None = None
    readonly_fields: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    search_fields: tuple[str, ...] | None = None
    fields: Mapping[str, FieldOptions] = field(default_factory=dict)
    can_create: bool = True
    can_edit: bool = True
    can_delete: bool = True
    permission: Permission | None = None
    relations: tuple[str, ...] | None = None
    readonly_relations: tuple[str, ...] = ()
    record_label: str | None = None
    expose_sensitive_fields: tuple[str, ...] = ()
    writable_protected_fields: tuple[str, ...] = ()
    actions: tuple[RecordAction, ...] = ()
    filter_fields: tuple[str, ...] | None = None

    def validate(self, schema: ModelSchema) -> None:
        names = set(schema.by_name)
        for option in (
            self.list_fields,
            self.edit_fields,
            self.create_fields,
            self.readonly_fields,
            self.exclude,
            self.search_fields,
            self.filter_fields,
            self.expose_sensitive_fields,
            self.writable_protected_fields,
            tuple(self.fields),
            (self.record_label,) if self.record_label else (),
        ):
            unknown = set(option or ()) - names
            if unknown:
                raise ValueError(f"Unknown fields in {schema.name}: {', '.join(sorted(unknown))}")
        if len({action.slug for action in self.actions}) != len(self.actions):
            raise ValueError("Duplicate record action slugs.")
        if self.search_fields is not None:
            if any(schema.by_name[name].kind != "string" for name in self.search_fields):
                raise ValueError("search_fields must contain string fields.")

    def visible_fields(self, schema: ModelSchema) -> tuple[Field, ...]:
        result = []
        for item in schema.fields:
            if item.name in self.exclude or (
                is_sensitive_field(item.name) and item.name not in self.expose_sensitive_fields
            ):
                continue
            override = self.fields.get(item.name, FieldOptions())
            result.append(
                replace(
                    item,
                    label=override.label or item.label,
                    kind=override.kind or item.kind,
                    parser=override.parser or item.parser,
                    formatter=override.formatter or item.formatter,
                    read_only=item.read_only
                    or override.read_only
                    or item.name in self.readonly_fields
                    or (
                        item.name.casefold() in PROTECTED_FIELDS
                        and item.name not in self.writable_protected_fields
                    ),
                )
            )
        return tuple(result)

    def form_fields(self, schema: ModelSchema, creating: bool) -> tuple[Field, ...]:
        selected = self.create_fields if creating else self.edit_fields
        visible = {item.name: item for item in self.visible_fields(schema)}
        ordered = (
            [visible[name] for name in selected if name in visible]
            if selected is not None
            else list(visible.values())
        )
        return tuple(item for item in ordered if not item.generated or not creating)

    def writable_fields(self, schema: ModelSchema, creating: bool) -> dict[str, Field]:
        return {
            item.name: item
            for item in self.form_fields(schema, creating)
            if not item.read_only and not item.generated and (creating or not item.primary_key)
        }

    def parse_values(
        self,
        schema: ModelSchema,
        data: Mapping[str, Any],
        creating: bool,
        *,
        managed_fields: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        writable = self.writable_fields(schema, creating)
        writable = {name: item for name, item in writable.items() if name not in managed_fields}
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}
        for name in data:
            if name == "__csrf":
                continue
            if name.startswith("__default__"):
                target = name.removeprefix("__default__")
                if not creating or target not in writable or not writable[target].has_default:
                    errors[name] = "This field has no writable default."
            elif name not in writable:
                errors[name] = "This field is not writable."
        for name, item in writable.items():
            if creating and item.has_default and data.get(f"__default__{name}") == "true":
                continue
            if name not in data:
                if creating and not item.has_default and not item.nullable:
                    errors[name] = "A value is required."
                continue
            try:
                values[name] = item.parse(data[name])
            except ValueError as exc:
                errors[name] = (
                    exc.args[0] if exc.args and isinstance(exc.args[0], Message) else str(exc)
                )
        if errors:
            raise ValidationError(errors)
        return values
