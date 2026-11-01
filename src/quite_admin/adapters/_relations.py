"""Shared validation before native relationship-write transactions."""

from quite_admin.errors import Conflict


def validate_selections(adapter, relations, selections):
    available = {relation.name: relation for relation in relations}
    for name, keys in selections.items():
        if name in available:
            schema = adapter.describe(available[name].target)
            for key in keys:
                schema.validate_key(key)
    if set(selections) - available.keys():
        raise Conflict("Unknown relationship.")
    return available
