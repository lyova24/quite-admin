"""Optional Pydantic validation; the ORM-independent core does not import it eagerly."""

from .errors import ValidationError


def validate_schema(schema):
    if schema is None:
        return
    try:
        from pydantic import BaseModel
    except ImportError as exc:
        raise ImportError("Install quite-admin[pydantic] to use form schemas.") from exc
    if not isinstance(schema, type) or not issubclass(schema, BaseModel):
        raise TypeError("Form schemas must be Pydantic 2 BaseModel subclasses.")


def field_errors(error):
    errors = {}
    for item in error.errors(include_input=False, include_context=False, include_url=False):
        location = item["loc"]
        name = str(location[0]) if location else "__all__"
        errors[name] = item["msg"]
    return ValidationError(errors)


def validate_payload(schema, values):
    if schema is None:
        return dict(values), dict(values)
    from pydantic import ValidationError as PydanticError

    try:
        payload = schema.model_validate(dict(values))
    except PydanticError as exc:
        raise field_errors(exc) from exc
    # Form permissions remain authoritative. Schema defaults/derived fields must
    # not silently turn into writes to columns that the user never submitted.
    normalized = payload.model_dump(exclude_unset=True)
    return {name: normalized[name] for name in values if name in normalized}, payload
