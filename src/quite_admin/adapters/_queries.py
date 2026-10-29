"""Native query expressions, called only after Query.validate()."""

import operator


def predicates(query, column, *, peewee=False):
    for item in query.filters:
        field = column(item.field)
        if item.operator == "is_null":
            if peewee:
                yield field.is_null(item.value)
            else:
                yield field.is_(None) if item.value else field.isnot(None)
        elif item.operator == "in":
            yield field.in_(item.value)
        else:
            operation = {
                "eq": operator.eq,
                "lt": operator.lt,
                "lte": operator.le,
                "gt": operator.gt,
                "gte": operator.ge,
            }[item.operator]
            yield operation(field, item.value)


def ordering(query, schema, column):
    order = query.order_by or schema.primary_keys[0].name
    yield column(order).desc() if query.descending else column(order).asc()
    for field in schema.primary_keys:
        if field.name != order:
            yield column(field.name).asc()


def tortoise_filters(statement, query):
    for item in query.filters:
        suffix = {
            "eq": "",
            "lt": "__lt",
            "lte": "__lte",
            "gt": "__gt",
            "gte": "__gte",
            "in": "__in",
            "is_null": "__isnull",
        }[item.operator]
        statement = statement.filter(**{item.field + suffix: item.value})
    return statement


def validate_query(adapter, model, query):
    schemas = {}
    if query.related:
        names = {item.relation for item in query.related if hasattr(item, "relation")}
        schemas = {
            relation.name: adapter.describe(relation.target)
            for relation in adapter.relations(model)
            if relation.name in names
        }
    query.validate(adapter.describe(model), related_schemas=schemas)
