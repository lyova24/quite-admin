"""SQLAlchemy table metadata shared by SQL reflection and GINO 1.x.

Keep this module compatible with SQLAlchemy 1.3 as well as 2.x.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import Column, Table
from sqlalchemy.exc import NoReferencedTableError

from quite_admin.relations import Relation


@dataclass(frozen=True)
class _Link:
    relation: Relation
    local: tuple[str, ...]
    remote: tuple[str, ...]
    reverse: bool = False
    through: Table | None = None
    through_local: tuple[str, ...] = ()
    through_remote: tuple[str, ...] = ()


def _unique(table, columns):
    return (
        set(columns) == {c.name for c in table.primary_key.columns}
        or any(
            getattr(c, "__visit_name__", "") == "unique_constraint"
            and set(columns) == {column.name for column in c.columns}
            for c in table.constraints
        )
        or any(
            index.unique
            and all(isinstance(expression, Column) for expression in index.expressions)
            and not any(name.endswith("_where") for name in index.dialect_kwargs)
            and set(columns) == {column.name for column in index.columns}
            for index in table.indexes
        )
    )


def _name(value):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


class SQLRelationMetadata:
    def _links(self, model):
        links = []
        for table in sorted(model.metadata.tables.values(), key=lambda item: item.fullname):
            if not table.primary_key.columns:
                continue
            constraints = sorted(
                table.foreign_key_constraints, key=lambda item: tuple(c.name for c in item.columns)
            )
            resolved = []
            for constraint in constraints:
                try:
                    target = constraint.referred_table
                except NoReferencedTableError:
                    continue
                if not target.primary_key.columns:
                    continue
                local = tuple(element.parent.name for element in constraint.elements)
                remote = tuple(element.column.name for element in constraint.elements)
                resolved.append((target, local, remote))
                if table is model:
                    name = _name("to_" + target.name + "_by_" + "_".join(local))
                    links.append(
                        _Link(
                            Relation(
                                name,
                                target,
                                "one_to_one" if _unique(table, local) else "many_to_one",
                                source_fields=local,
                                can_detach=all(table.c[n].nullable for n in local),
                                read_only=bool(
                                    set(local) & {c.name for c in model.primary_key.columns}
                                ),
                            ),
                            local,
                            remote,
                        )
                    )
                if target is model:
                    name = _name("from_" + table.name + "_by_" + "_".join(local))
                    links.append(
                        _Link(
                            Relation(
                                name,
                                table,
                                "one_to_one" if _unique(table, local) else "one_to_many",
                                target_fields=local,
                                can_detach=all(table.c[n].nullable for n in local),
                                mutates_target=True,
                                read_only=bool(
                                    set(local) & {c.name for c in table.primary_key.columns}
                                ),
                            ),
                            remote,
                            local,
                            reverse=True,
                        )
                    )
            # Only pure junctions have an unambiguous many-to-many write contract.
            if len(resolved) != 2:
                continue
            covered = set(resolved[0][1]) | set(resolved[1][1])
            if covered != {c.name for c in table.columns} or not _unique(table, covered):
                continue
            for left, right in (resolved, resolved[::-1]):
                if left[0] is model:
                    target, target_columns, target_remote = right
                    links.append(
                        _Link(
                            Relation(
                                _name(target.name + "_via_" + table.name + "_" + "_".join(left[1])),
                                target,
                                "many_to_many",
                            ),
                            left[2],
                            target_remote,
                            through=table,
                            through_local=left[1],
                            through_remote=target_columns,
                        )
                    )
        return {link.relation.name: link for link in links}
