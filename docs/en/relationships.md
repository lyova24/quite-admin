# Relationships

Relationships appear inside the record's create form and unified record page and share the **Save** button
with scalar fields. One-to-one and many-to-one relations use a single selector; one-to-many
and many-to-many relations allow multiple selections. Targets must already exist.
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

## Search and selection

Use **Choose records** to open a picker. Search uses the target collection's visible
`search_fields` (visible strings by default); results load 25 at a time in stable
primary-key order. Previous/Next reaches the complete candidate set, including records
beyond the old 1000-candidate limit. Only keys and permitted record labels reach the browser.
Selected chips stay selected across search queries and pages; × removes a selection.
The picker supports Tab, Space/Enter and Escape. Searching never submits the record form.
Selections are committed together with scalar fields by **Save changes**.

Up to 1000 records can be selected in one relationship. Larger existing memberships
are read-only to prevent partial updates. Without JavaScript, the native selector
contains the first 25 candidates plus existing selections; enable JavaScript to search
all records. A failed request preserves selections and offers Retry.

The read-only options endpoint checks parent create/edit permission, target list/view
permission, field restrictions and reverse-link edit permission on every request.
Search does not include hidden fields. The built-in script is self-hosted and loaded
with SRI; CSP permits its exact SHA-256 hash on editable relationship forms only.
Inline scripts and arbitrary same-origin scripts remain blocked. Custom `form.html`
overrides can reuse the standard picker markup, `picker_messages` and `editor.endpoint`;
`base.html` automatically loads the supplied `scripts`.

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
