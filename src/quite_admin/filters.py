"""Allowlisted HTML filter controls over the existing typed query contract."""

from .i18n import Message
from .schema import Filter

RANGE_KINDS = {"integer", "number", "date", "datetime", "time"}
OPERATORS = {"eq": "=", "gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "is_null": ""}


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
            operators = ("eq", "gt", "gte", "lt", "lte")
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


def presentation(fields, relations, active, translate):
    """Expose only allowlisted fields and group inclusive bounds into one condition."""
    descriptors = [
        {
            "id": "f." + field.name,
            "label": field.label,
            "kind": field.kind,
            "nullable": field.nullable,
            "choices": field.choices,
        }
        for field in fields
    ]
    descriptors.extend(
        {
            "id": "r." + item["relation"].name,
            "label": item["relation"].label,
            "kind": "relation",
            "endpoint": item["endpoint"],
            "choices": item["choices"],
        }
        for item in relations
    )
    by_parameter = {item["parameter"]: item for item in active}
    grouped, consumed = [], set()
    for item in active:
        name = item["parameter"]
        if name in consumed:
            continue
        if "field" not in item:
            grouped.append(
                {
                    "id": name,
                    "parameters": [name],
                    "operator": "eq",
                    "values": [item["value"]],
                    "label": item["label"],
                }
            )
            continue
        field, operator, value = item["field"], item["operator"], item["value"]
        prefix = "f." + field.name
        lower, upper = by_parameter.get(prefix + ".gte"), by_parameter.get(prefix + ".lte")
        if operator in {"gte", "lte"} and lower and upper:
            names = [prefix + ".gte", prefix + ".lte"]
            consumed.update(names)
            grouped.append(
                {
                    "id": prefix,
                    "parameters": names,
                    "operator": "between",
                    "values": [lower["value"], upper["value"]],
                    "label": field.label + " " + lower["value"] + " – " + upper["value"],
                }
            )
            continue
        if operator == "is_null":
            text = translate("Is NULL" if value == "true" else "Is not NULL")
        else:
            text = (
                OPERATORS[operator]
                + " "
                + (
                    translate("True" if value.lower() in {"true", "1"} else "False")
                    if field.kind == "boolean"
                    else value
                )
            )
        grouped.append(
            {
                "id": prefix,
                "parameters": [name],
                "operator": operator,
                "values": [value],
                "label": field.label + " " + text,
            }
        )
    return descriptors, grouped


def messages(translate):
    return {
        key: translate(value)
        for key, value in {
            "add": "Add filter",
            "find": "Find a field…",
            "back": "Back",
            "operator": "Condition",
            "value": "Value",
            "eq": "Equals",
            "gt": "Greater than",
            "gte": "At least",
            "lt": "Less than",
            "lte": "At most",
            "between": "Between",
            "null": "Is NULL",
            "not_null": "Is not NULL",
            "from": "From",
            "to": "To",
            "apply": "Apply filter",
            "cancel": "Cancel",
            "required": "A value is required.",
            "empty": "No matching fields.",
            "search": "Search related records",
            "loading": "Loading…",
            "no_records": "No matching records.",
            "failed": "Could not load records. Try again.",
            "retry": "Retry",
            "previous": "Previous",
            "next": "Next",
            "true": "True",
            "false": "False",
            "selected": "Selected",
            "conflict": "This condition already exists. Edit the existing filter.",
            "hint": "All conditions must match.",
            "iso": "Use an ISO date or time, including a timezone if needed.",
        }.items()
    }
