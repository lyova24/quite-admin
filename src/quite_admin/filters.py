"""Allowlisted HTML filter controls over the existing typed query contract."""

import json
import re
from datetime import datetime, timedelta

from .i18n import Message
from .schema import FILTER_OPERATORS, LEGACY_FILTER_OPERATORS, TEXT_FILTER_OPERATORS, Filter

RANGE_KINDS = {"integer", "number", "date", "datetime", "time"}
OPERATORS = {
    "eq": "=",
    "ne": "≠",
    "gt": ">",
    "gte": "≥",
    "lt": "<",
    "lte": "≤",
    "is_null": "",
    "in": "Is one of",
    "icontains": "Contains",
    "not_icontains": "Does not contain",
    "istartswith": "Starts with",
    "iendswith": "Ends with",
    "is_empty": "",
    "on": "On date",
}


def supported(resource):
    adapter = getattr(resource, "adapter", None)
    return getattr(adapter, "supported_filter_operators", LEGACY_FILTER_OPERATORS)


def field_operators(field, allowed=FILTER_OPERATORS):
    if field.kind in {"json", "binary", "unsupported"}:
        result = []
    elif field.kind == "boolean":
        result = ["eq"]
    elif field.choices or field.kind == "enum":
        result = ["eq", "ne", "in"]
    elif field.kind == "string":
        result = ["icontains", "not_icontains", "eq", "ne", "istartswith", "iendswith", "in"]
    elif field.kind in RANGE_KINDS:
        result = ["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    else:
        result = ["eq", "ne", "in"]
    result = [op for op in result if op in allowed]
    if field.kind == "string" and not field.choices and "eq" in allowed:
        result.append("is_empty")
    if field.kind == "datetime" and {"gte", "lt"} <= set(allowed):
        result.insert(0, "on")
    if field.nullable and "is_null" in allowed:
        result.append("is_null")
    return tuple(result)


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


def parameters(fields, allowed=FILTER_OPERATORS, params=None):
    result = {
        f"f.{field.name}.{op}": (field, op)
        for field in fields
        for op in field_operators(field, allowed)
    }
    base_names = frozenset(result)
    for name in params or ():
        match = re.fullmatch(r"(.+)~([1-9][0-9]?)", name)
        if match and int(match[2]) <= 50 and match[1] in base_names:
            result[name] = result[match[1]]
    return result


def parse(resource, fields, params):
    allowed = parameters(fields, supported(resource), params)
    filters, errors, active = [], {}, []
    for name, raw in params.items():
        if not name.startswith("f."):
            continue
        if name not in allowed or len(params.getlist(name)) != 1:
            raise ValueError("Invalid filter.")
        if not raw:
            continue
        field, operator = allowed[name]
        slot = re.search(r"~[1-9][0-9]?$", name)
        active.append(
            {
                "parameter": name,
                "field": field,
                "operator": operator,
                "value": raw,
                "slot": slot[0] if slot else "",
            }
        )
        try:
            if len(raw) > (8192 if operator == "in" else 500):
                raise ValueError("Filter value is too long.")
            if operator in {"is_null", "is_empty"}:
                if raw not in {"true", "false"}:
                    raise ValueError(Message("Choose true or false."))
                if operator == "is_empty":
                    op = "eq" if raw == "true" else "ne"
                    if op not in supported(resource):
                        raise ValueError(Message("This adapter does not support this condition."))
                    items = [Filter(field.name, op, "")]
                else:
                    items = [Filter(field.name, "is_null", raw == "true")]
            elif operator == "in":
                try:
                    values = json.loads(raw)
                except (ValueError, TypeError) as exc:
                    raise ValueError(Message("Enter a JSON list of text values.")) from exc
                if (
                    not isinstance(values, list)
                    or not 1 <= len(values) <= 100
                    or any(not isinstance(v, str) or len(v) > 500 for v in values)
                ):
                    raise ValueError(Message("Choose between 1 and 100 values."))
                items = [Filter(field.name, "in", tuple(field.parse(v) for v in values))]
            elif operator == "on":
                try:
                    start = datetime.fromisoformat(raw)
                    if any((start.hour, start.minute, start.second, start.microsecond)):
                        raise ValueError
                    end = start + timedelta(days=1)
                except (ValueError, OverflowError) as exc:
                    raise ValueError(
                        Message("Choose a date, with an optional UTC offset.")
                    ) from exc
                items = [Filter(field.name, "gte", start), Filter(field.name, "lt", end)]
            else:
                value = raw if operator in TEXT_FILTER_OPERATORS else field.parse(raw)
                items = [Filter(field.name, operator, value)]
            for item in items:
                item.validate(resource.schema)
            filters.extend(items)
        except ValueError as exc:
            errors[name] = (
                exc.args[0] if exc.args and isinstance(exc.args[0], Message) else str(exc)
            )
    if len(filters) > 50:
        errors["__all__"] = "At most 50 filters are supported."
    for item in active:
        if item["operator"] != "gte":
            continue
        upper_name = "f." + item["field"].name + ".lte" + item["slot"]
        upper = next((other for other in active if other["parameter"] == upper_name), None)
        if upper is None or item["parameter"] in errors or upper_name in errors:
            continue
        try:
            if item["field"].parse(item["value"]) > upper["field"].parse(upper["value"]):
                errors[upper_name] = (
                    "The upper bound must be greater than or equal to the lower bound."
                )
        except TypeError:
            errors[upper_name] = "Use compatible date and time values."
    return tuple(filters), errors, active


def presentation(fields, relations, active, translate, allowed=FILTER_OPERATORS):
    """Expose only allowlisted fields and group inclusive bounds into one condition."""
    descriptors = [
        {
            "id": "f." + field.name,
            "label": field.label,
            "kind": field.kind,
            "nullable": field.nullable,
            "choices": field.choices,
            "operators": field_operators(field, allowed),
            "supports_not_empty": "ne" in allowed,
        }
        for field in fields
    ]
    descriptors.extend(
        {
            "id": "r." + item["relation"].name,
            "label": item["relation"].label,
            "kind": "relation",
            "endpoint": item["endpoint"],
            "search_labels": [
                f.label
                for f in item["target"].options.visible_fields(item["target"].schema)
                if f.kind == "string"
                and (
                    item["target"].options.search_fields is None
                    or f.name in item["target"].options.search_fields
                )
            ],
            "key_search": getattr(item["target"].adapter, "supports_key_search", False)
            and all(
                f.name
                in {v.name for v in item["target"].options.visible_fields(item["target"].schema)}
                for f in item["target"].schema.primary_keys
            ),
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
        raw_value = value
        prefix = "f." + field.name
        suffix = item.get("slot", "")
        lower = by_parameter.get(prefix + ".gte" + suffix)
        upper = by_parameter.get(prefix + ".lte" + suffix)
        if operator in {"gte", "lte"} and lower and upper:
            names = [prefix + ".gte" + suffix, prefix + ".lte" + suffix]
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
        elif operator == "is_empty":
            text = translate("Is empty text" if value == "true" else "Is not empty text")
        elif operator == "in":
            try:
                values = json.loads(value)
                value = (
                    ", ".join(values)
                    if isinstance(values, list) and all(isinstance(v, str) for v in values)
                    else value
                )
            except ValueError:
                pass
            text = translate("Is one of") + " " + value
        elif operator in TEXT_FILTER_OPERATORS or operator == "on":
            text = translate(OPERATORS[operator]) + " " + value.replace("T00:00:00", " ").strip()
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
                "values": [raw_value],
                "label": field.label + " " + text,
            }
        )
    return descriptors, grouped


def messages(translate):
    return {
        key: translate(value)
        for key, value in {
            "add": "Add filter",
            "close": "Close",
            "remove": "Remove",
            "another": "Add another condition",
            "ne": "Does not equal",
            "icontains": "Contains",
            "not_icontains": "Does not contain",
            "istartswith": "Starts with",
            "iendswith": "Ends with",
            "in": "Is one of",
            "on": "On date",
            "empty": "Is empty text",
            "not_empty": "Is not empty text",
            "no_fields": "No matching fields.",
            "find_values": "Search values",
            "one_per_line": "One value per line",
            "any_value": "Match any selected value; other conditions must also match.",
            "date": "Date",
            "timezone": "UTC offset (optional)",
            "day_hint": (
                "Includes the whole day. Leave the offset empty for database-local "
                "time, or enter Z / ±HH:MM."
            ),
            "text_example": "For example, Alex",
            "text_hint": (
                "Partial text ignores case. %, _ and ! are literal characters; NULL is separate."
            ),
            "invalid": "Enter valid values.",
            "max_values": "Choose between 1 and 100 values.",
            "search_id": "Search text or an exact ID. Searchable fields:",
            "search_text": "Searchable fields:",
            "type_string": "Text",
            "type_integer": "Integer",
            "type_number": "Number",
            "type_boolean": "Boolean",
            "type_enum": "Choice",
            "type_uuid": "UUID",
            "type_date": "Date",
            "type_datetime": "Date and time",
            "type_time": "Time",
            "type_relation": "Related record",
            "type_json": "JSON",
            "type_binary": "Binary",
            "type_unsupported": "Other",
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
