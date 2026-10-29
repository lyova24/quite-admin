"""Allowlisted HTML filter controls over the existing typed query contract."""

from .i18n import Message
from .schema import Filter

RANGE_KINDS = {"integer", "number", "date", "datetime", "time"}
OPERATORS = {"eq": "=", "gte": "≥", "lte": "≤", "is_null": ""}


def controls(resource):
    selected = resource.options.filter_fields
    fields = resource.options.visible_fields(resource.schema)
    if selected is not None:
        by_name = {field.name: field for field in fields}
        fields = tuple(by_name[name] for name in selected if name in by_name)
    return tuple(
        field
        for field in fields
        if field.nullable or field.kind not in {"json", "binary", "unsupported"}
    )


def parameters(fields):
    result = {}
    for field in fields:
        if field.kind in RANGE_KINDS:
            operators = ("gte", "lte")
        elif field.kind in {"json", "binary", "unsupported"}:
            operators = ()
        else:
            operators = ("eq",)
        if field.nullable:
            operators += ("is_null",)
        for operator in operators:
            result[f"f.{field.name}.{operator}"] = (field, operator)
    return result


def parse(resource, fields, params):
    allowed = parameters(fields)
    filters, errors, active = [], {}, []
    for name, raw in params.items():
        if not name.startswith("f."):
            continue
        if name not in allowed or len(params.getlist(name)) != 1:
            raise ValueError("Invalid filter.")
        if not raw:
            continue
        field, operator = allowed[name]
        active.append({"parameter": name, "field": field, "operator": operator, "value": raw})
        try:
            if len(raw) > 500:
                raise ValueError("Filter value is too long.")
            if operator == "is_null":
                if raw not in {"true", "false"}:
                    raise ValueError("Choose true or false.")
                value = raw == "true"
            else:
                value = field.parse(raw)
            item = Filter(field.name, operator, value)
            item.validate(resource.schema)
            filters.append(item)
        except ValueError as exc:
            errors[name] = (
                exc.args[0] if exc.args and isinstance(exc.args[0], Message) else str(exc)
            )
    if len(filters) > 50:
        errors["__all__"] = "At most 50 filters are supported."
    for field in fields:
        lower = next(
            (item for item in filters if item.field == field.name and item.operator == "gte"), None
        )
        upper = next(
            (item for item in filters if item.field == field.name and item.operator == "lte"), None
        )
        if lower and upper:
            try:
                if lower.value > upper.value:
                    errors[f"f.{field.name}.lte"] = (
                        "The upper bound must be greater than or equal to the lower bound."
                    )
            except TypeError:
                errors[f"f.{field.name}.lte"] = "Use compatible date and time values."
    return tuple(filters), errors, active
