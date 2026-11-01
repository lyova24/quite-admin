"""Native query expressions, called only after Query.validate()."""

import operator

from quite_admin.pagination import window_condition, window_ordering
from quite_admin.schema import TEXT_FILTER_OPERATORS


def predicates(query, column, *, peewee=False, text_column=None):
    for item in query.filters:
        field = column(item.field)
        if item.operator == "is_null":
            if peewee:
                yield field.is_null(item.value)
            else:
                yield field.is_(None) if item.value else field.isnot(None)
        elif item.operator in TEXT_FILTER_OPERATORS:
            field = (text_column or column)(item.field)
            method = {
                "icontains": "contains",
                "not_icontains": "contains",
                "istartswith": "startswith",
                "iendswith": "endswith",
            }[item.operator]
            if peewee:
                expression = getattr(field, method)(item.value)
            else:
                literal = item.value.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                pattern = ("%" if method != "startswith" else "") + literal
                pattern += "%" if method != "endswith" else ""
                expression = field.ilike(pattern, escape="!")
            yield ~expression if item.operator == "not_icontains" else expression
        elif item.operator == "in":
            yield field.in_(item.value)
        else:
            operation = {
                "eq": operator.eq,
                "ne": operator.ne,
                "lt": operator.lt,
                "lte": operator.le,
                "gt": operator.gt,
                "gte": operator.ge,
            }[item.operator]
            yield operation(field, item.value)


def search_predicate(query, column, *, peewee=False, text_column=None):
    expressions = []
    if query.search:
        for name in query.search_fields:
            field = (text_column or column)(name)
            if peewee:
                expressions.append(field.contains(query.search))
            else:
                literal = query.search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
                expressions.append(field.ilike("%" + literal + "%", escape="!"))
    if query.search_key is not None:
        key_parts = [column(name) == value for name, value in query.search_key.items()]
        key_match = key_parts[0]
        for part in key_parts[1:]:
            key_match = key_match & part
        expressions.append(key_match)
    if not expressions:
        return None
    search = expressions[0]
    for expression in expressions[1:]:
        search = search | expression
    return search


def ordering(query, schema, column):
    order = query.order_by or schema.primary_keys[0].name
    yield column(order).desc() if query.descending else column(order).asc()
    for field in schema.primary_keys:
        if field.name != order:
            yield column(field.name).asc()


def paginate(statement, query, schema, column, *, after=None, before=None, window=False):
    """Apply the same stable ordering to SQLAlchemy, GINO and Peewee reads."""
    if window:
        condition = window_condition(
            schema, query, after if after is not None else before, before is not None, column
        )
        if condition is not None:
            statement = statement.where(condition)
        expressions = window_ordering(schema, query, before is not None, column)
    else:
        expressions = ordering(query, schema, column)
    return statement.order_by(*expressions).offset(query.offset).limit(query.limit + int(window))


def tortoise_filters(statement, query):
    for item in query.filters:
        if item.operator == "not_icontains":
            statement = statement.exclude(**{item.field + "__icontains": item.value}).filter(
                **{item.field + "__isnull": False}
            )
            continue
        suffix = {
            "eq": "",
            "ne": "__not",
            "icontains": "__icontains",
            "istartswith": "__istartswith",
            "iendswith": "__iendswith",
            "lt": "__lt",
            "lte": "__lte",
            "gt": "__gt",
            "gte": "__gte",
            "in": "__in",
            "is_null": "__isnull",
        }[item.operator]
        statement = statement.filter(**{item.field + suffix: item.value})
        if item.operator == "ne":
            statement = statement.filter(**{item.field + "__isnull": False})
    return statement


def validate_query(adapter, model, query):
    schema = adapter.describe(model)
    schemas = {}
    if query.related:
        names = {item.relation for item in query.related if hasattr(item, "relation")}
        schemas = {
            relation.name: adapter.describe(relation.target)
            for relation in adapter.relations(model)
            if relation.name in names
        }
    query.validate(schema, related_schemas=schemas)
    return schema
