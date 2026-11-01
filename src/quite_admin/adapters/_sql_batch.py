"""Bounded source/target joins; compatible with SQLAlchemy 1.3 and 2.x."""

from sqlalchemy import and_, select, tuple_


def batch_statement(table, link, source_fields, target_fields, keys, limit, *, legacy=False):
    source = table.alias("qa_source")
    target = link.relation.target.alias("qa_target")
    source_columns = [source.c[name] for name in source_fields]
    columns = [column.label(f"qa_parent_{i}") for i, column in enumerate(source_columns)]
    columns.extend(target.c[name].label(f"qa_target_{i}") for i, name in enumerate(target_fields))
    if link.through is not None:
        through = link.through.alias("qa_through")
        joined = source.join(
            through,
            and_(
                *(
                    source.c[local] == through.c[column]
                    for local, column in zip(link.local, link.through_local, strict=True)
                )
            ),
        ).join(
            target,
            and_(
                *(
                    target.c[remote] == through.c[column]
                    for remote, column in zip(link.remote, link.through_remote, strict=True)
                )
            ),
        )
    else:
        joined = source.join(
            target,
            and_(
                *(
                    source.c[local] == target.c[remote]
                    for local, remote in zip(link.local, link.remote, strict=True)
                )
            ),
        )
    values = [tuple(key[name] for name in source_fields) for key in keys]
    condition = (
        source_columns[0].in_([value[0] for value in values])
        if len(source_columns) == 1
        else tuple_(*source_columns).in_(values)
    )
    statement = select(columns) if legacy else select(*columns)
    return (
        statement.select_from(joined)
        .where(condition)
        .order_by(*source_columns, *target.primary_key)
        .limit(limit)
    )
