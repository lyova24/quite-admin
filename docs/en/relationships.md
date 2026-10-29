# Relationships

Relationships appear inside the record's create form and unified record page and share the **Save** button
with scalar fields. One-to-one and many-to-one relations use a single selector; one-to-many
and many-to-many relations use a multiple selector. Targets must already exist.
The record page displays values and allows editing immediately when permitted. Users with only
view permission see the same page with read-only fields and relationships.

Supported backends: synchronous/asynchronous SQLAlchemy, synchronous/asynchronous SQL reflection,
Peewee and Tortoise. ORM adapters use native ORM operations; SQL reflection uses database constraints.
Scalar changes and all submitted relationship changes commit together or roll back together.

```python
from quite_admin import ModelOptions

admin.register(Product, options=ModelOptions(
    relations=("tags",),
    readonly_relations=(),
    record_label="name",
))
```

`relations=None` discovers relationships automatically; `relations=()` hides them.
`readonly_relations` displays selected records without allowing changes.
Set `record_label` on the target model to choose its selector label. Otherwise common names
such as `name` and `title` are used, falling back to primary keys. Excluded fields are never labels.

Both ends must be registered with the same adapter. A target must allow listing and viewing.
Changing a reverse foreign key also requires edit permission and writable foreign-key fields
on the target. Hidden/read-only source fields and hidden target foreign keys remain protected.
Scalar foreign-key inputs are replaced by selectors when the relationship is displayed.

Omitting a relationship preserves it. Submitting an empty selection clears it when nullable.
Required foreign keys and delete-orphan relationships cannot be detached by the editor;
it never deletes target records. Move a required child by choosing another parent on its own form.
Invalid keys, unavailable targets and failed constraints reject the entire save.

Selectors display up to 1000 candidates, retaining existing selections outside that window.
If a relationship already contains more than 1000 selected records, it is read-only to prevent
partial updates. Use an application-specific UI for larger collections.

Reflection recognizes pure many-to-many junctions with two foreign-key constraints and a
unique combined key. Junctions with extra payload columns require an application adapter.
One-to-one detection accepts primary keys, unique constraints and full unique indexes;
partial unique indexes do not guarantee global cardinality. MySQL represents reflected
unique constraints as indexes, which are supported as well.
SQLAlchemy uses mapped `relationship()` definitions; view-only and dynamic/write-only relationships
are read-only. Peewee uses foreign keys, backrefs and `ManyToManyField`; Tortoise uses native relations.

Custom adapters may optionally implement the exported `RelationAdapter` protocol:
`relations()`, paginated `related()` and atomic `save_relations()`. The scalar `Adapter` contract
is unchanged. Metadata is represented by `Relation` and has no template dependencies.

The local demo includes Product–Tag (M:N), Customer–Order (1:N) and Customer–Profile (1:1).
