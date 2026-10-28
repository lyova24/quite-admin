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

Action = Literal["list", "view", "create", "edit", "delete"]
Permission = Callable[["Request", "Identity", Action], bool | Awaitable[bool]]


@dataclass(frozen=True)
class FieldOptions:
    label: str | None = None
    read_only: bool = False
    help_text: str = ""


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

    def validate(self, schema: ModelSchema) -> None:
        names = set(schema.by_name)
        for option in (
            self.list_fields,
            self.edit_fields,
            self.create_fields,
            self.readonly_fields,
            self.exclude,
            self.search_fields,
            tuple(self.fields),
        ):
            unknown = set(option or ()) - names
            if unknown:
                raise ValueError(f"Unknown fields in {schema.name}: {', '.join(sorted(unknown))}")
        if self.search_fields is not None:
            if any(schema.by_name[name].kind != "string" for name in self.search_fields):
                raise ValueError("search_fields must contain string fields.")

    def visible_fields(self, schema: ModelSchema) -> tuple[Field, ...]:
        result = []
        for item in schema.fields:
            if item.name in self.exclude:
                continue
            override = self.fields.get(item.name, FieldOptions())
            result.append(
                replace(
                    item,
                    label=override.label or item.label,
                    read_only=item.read_only
                    or override.read_only
                    or item.name in self.readonly_fields,
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
        self, schema: ModelSchema, data: Mapping[str, Any], creating: bool
    ) -> dict[str, Any]:
        writable = self.writable_fields(schema, creating)
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
