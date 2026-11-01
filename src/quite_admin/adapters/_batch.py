"""Validation and scalar grouping for optional bounded relationship reads."""

from quite_admin.relations import RelatedBatch
from quite_admin.schema import Query


def prepare_batch(adapter, model, name, keys, limit, columns=None):
    if type(limit) is not int or not 1 <= limit <= 10001:
        raise ValueError("Batch limit must be between 1 and 10001.")
    if len(keys) > 1000:
        raise ValueError("At most 1000 source keys are supported.")
    schema = adapter.describe(model)
    tokens = []
    for key in keys:
        schema.validate_key(key)
        tokens.append(schema.record_key(dict(key)))
    if len(tokens) != len(set(tokens)):
        raise ValueError("Duplicate source keys.")
    relation = next((item for item in adapter.relations(model) if item.name == name), None)
    if relation is None:
        raise ValueError("Unknown relationship.")
    target_schema = adapter.describe(relation.target)
    Query(columns=columns).validate(target_schema)
    return schema, target_schema, relation


def batch_fields(schema, columns):
    if columns is None:
        return schema.fields
    selected = set(columns) | {field.name for field in schema.primary_keys}
    return tuple(field for field in schema.fields if field.name in selected)


def finish_batch(schema, target_schema, keys, rows, limit, columns=None):
    result = {schema.record_key(dict(key)): {} for key in keys}
    for row in rows:
        key = {field.name: row[f"qa_parent_{i}"] for i, field in enumerate(schema.primary_keys)}
        record = {
            field.name: row[f"qa_target_{i}"]
            for i, field in enumerate(batch_fields(target_schema, columns))
        }
        result[schema.record_key(key)][target_schema.record_key(record)] = Query(
            columns=columns
        ).project(record)
    return RelatedBatch(
        {token: list(records.values()) for token, records in result.items()},
        truncated=len(rows) >= limit,
    )
