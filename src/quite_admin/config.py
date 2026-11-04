from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Literal

from ._display import _http_url
from ._validation import validate_schema
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


@dataclass(init=False)
class RecordAction:
    slug: str
    label: str
    handler: Callable[[Operation], Mapping[str, Any] | None | Awaitable[Mapping[str, Any] | None]]
    permission: Permission | None = None
    required_permission: Action = "edit"
    bulk: bool = False

    def __init__(
        self,
        slug: str,
        label: str,
        handler: Callable[
            [Operation], Mapping[str, Any] | None | Awaitable[Mapping[str, Any] | None]
        ],
        permission: Permission | None = None,
        required_permission: Action = "edit",
        bulk: bool = False,
    ) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", slug):
            raise ValueError("Action slugs must contain letters, digits, hyphens or underscores.")
        if required_permission not in {"list", "view", "create", "edit", "delete"}:
            raise ValueError("Unknown required action permission.")
        if not isinstance(bulk, bool):
            raise ValueError("bulk must be a boolean.")
        self.slug = slug
        self.label = label
        self.handler = handler
        self.permission = permission
        self.required_permission = required_permission
        self.bulk = bulk


@dataclass(frozen=True)
class FieldOptions:
    label: str | None = None
    read_only: bool = False
    help_text: str = ""
    kind: str | None = None
    parser: Callable[[Any], Any] | None = None
    formatter: Callable[[Any], str] | None = None
    template: str | None = None
    display: Literal["text", "url", "json", "multiline"] | None = None
    url_template: str | None = None


_DEFAULT_FIELD_OPTIONS = FieldOptions()


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
    group: str | None = None
    list_editable: tuple[str, ...] | None = None
    pagination: Literal["offset", "cursor"] = "offset"
    input_fields: tuple[Field, ...] = ()
    create_schema: type[Any] | None = None
    update_schema: type[Any] | None = None
    create_handler: Callable[[Operation, Any], Any | Awaitable[Any]] | None = None
    update_handler: Callable[..., Any] | None = None
    bulk_delete: bool = True

    def validate(self, schema: ModelSchema) -> None:
        if not isinstance(self.bulk_delete, bool):
            raise ValueError("bulk_delete must be a boolean.")
        if any(
            item.display not in {None, "text", "url", "json", "multiline"}
            for item in self.fields.values()
        ):
            raise ValueError("display must be text, url, json, multiline or None.")
        for item in self.fields.values():
            if item.url_template is None:
                continue
            template = item.url_template
            if (
                not isinstance(template, str)
                or "{value}" not in template
                or "{" in template.replace("{value}", "")
                or "}" in template.replace("{value}", "")
                or item.display not in {None, "url"}
                or _http_url(template.replace("{value}", "value")) is None
            ):
                raise ValueError(
                    "url_template must be an HTTP(S) URL containing only {value} placeholders."
                )
        validate_schema(self.create_schema)
        validate_schema(self.update_schema)
        if any(
            handler is not None and not callable(handler)
            for handler in (self.create_handler, self.update_handler)
        ):
            raise TypeError("Model write handlers must be callable.")
        if self.pagination not in {"offset", "cursor"}:
            raise ValueError("pagination must be offset or cursor.")
        if self.group is not None and (not isinstance(self.group, str) or not self.group.strip()):
            raise ValueError("group must be a nonempty label or None.")
        fields = schema.by_name
        names = set(fields)
        inputs = {item.name: item for item in self.input_fields}
        if len(inputs) != len(self.input_fields) or inputs.keys() & names:
            raise ValueError("input_fields must have unique names distinct from model fields.")
        if any(item.primary_key or item.generated or item.foreign_key for item in inputs.values()):
            raise ValueError("Input fields cannot be primary keys, generated or foreign keys.")
        for option in (
            self.list_fields,
            self.list_editable,
            self.search_fields,
            self.filter_fields,
            (self.record_label,) if self.record_label else (),
        ):
            unknown = set(option or ()) - names
            if unknown:
                raise ValueError(
                    f"Unknown model fields in {schema.name}: {', '.join(sorted(unknown))}"
                )
        for option in (
            self.edit_fields,
            self.create_fields,
            self.readonly_fields,
            self.exclude,
            self.expose_sensitive_fields,
            self.writable_protected_fields,
            tuple(self.fields),
        ):
            unknown = set(option or ()) - (names | inputs.keys())
            if unknown:
                raise ValueError(f"Unknown fields in {schema.name}: {', '.join(sorted(unknown))}")
        if len({action.slug for action in self.actions}) != len(self.actions):
            raise ValueError("Duplicate record action slugs.")
        if self.search_fields is not None:
            if any(fields[name].kind != "string" for name in self.search_fields):
                raise ValueError("search_fields must contain string fields.")

    def visible_fields(self, schema: ModelSchema) -> tuple[Field, ...]:
        return self._fields(schema, form=False)

    def _fields(self, schema: ModelSchema, *, form: bool) -> tuple[Field, ...]:
        result = []
        inputs = {item.name for item in self.input_fields} if form else set()
        for item in (*schema.fields, *(self.input_fields if form else ())):
            override = self.fields.get(item.name, _DEFAULT_FIELD_OPTIONS)
            kind = override.kind or item.kind
            if (
                item.name in self.exclude
                or (
                    item.name not in inputs
                    and is_sensitive_field(item.name)
                    and item.name not in self.expose_sensitive_fields
                )
                or (not form and kind == "password")
            ):
                continue
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
        visible = {item.name: item for item in self._fields(schema, form=True)}
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
