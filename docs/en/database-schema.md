# Interactive database schema

Open **Database schema** in the navigation (`/admin/schema`, or your mount prefix).
The diagram includes every registered table you can list and view. All these tables
are selected by default, including tables without relationships, when no more than 100
are available. Larger schemas start with no tables selected; choose the tables you need
in the table picker, or select **Show all**. It uses adapter metadata;
opening or rearranging the diagram does not read or modify record values.

[![Database schema with the table picker and expanded M:N junction](../assets/screenshots/database-schema.png)](../assets/screenshots/database-schema.png)

The schema uses the available page height below the header. The wider table picker
provides more room for labels and group controls; on short screens its contents
scroll while the diagram remains usable. The picker belongs to the schema workspace;
the complete table catalog for opening record lists is in the **Table list** view on Home.
This layout preserves the initial manual-selection guard for more than 100 permitted tables.

## Explore the diagram

- **Tables** opens the table picker. Search by table label, table name or configured group, use checkboxes
  to choose visible tables, or select **Show all** / **Hide all**. Search narrows the
  picker choices without changing the diagram. Clicking a table name centers it.
- A group checkbox selects or clears all its tables at once. Groups follow
  `ModelOptions(group="Sales")`, as in Home's **Table list** view. A mixed checkbox means only
  some tables in the group are selected; its count always covers the whole group.
  Searching hides nonmatching choices, but a group checkbox still changes every table
  in that group, including those hidden by search. Searching for a group name shows
  all its tables. Tables without a group and unregistered junctions remain individual choices.
- Cards initially show primary keys and relationship fields. Click a card, or focus it
  and press Enter/Space, to show its remaining visible fields. Click again to collapse it.
- Hover over a card or focus it to reveal **Show only related tables**. This keeps
  that table and its directly connected neighbours from the current selection.
  Press the same button again to restore the previous tables, positions and zoom.
  The active button stays visible; on touch screens card buttons are always shown.
  Choosing another card's button switches the related view within the original selection.
  Changing table or group checkboxes ends this temporary view and uses the edited selection.
- Lines connect the participating fields. Their labels and end markers distinguish
  **1:1 · o2o**, **1:N · o2m** and **N:M · m2m**. Selecting a table highlights its links.
- Click an **N:M** label to reveal the junction table and its two **1:N** links. Click
  either link's collapse control to return to the logical M:N relationship. If the
  junction is already registered, its existing card is reused. Otherwise its metadata
  card becomes available in the table picker when revealed.
- Drag a card to move it; drag empty canvas to pan. The wheel pans; Ctrl/⌘ + wheel or
  the +/− buttons zoom. **Fit schema** fits visible tables; **Auto layout** also resets
  manual positions. Moving any table fixes the positions of every visible table until
  **Auto layout** is used. Automatic layout accounts for expanded cards and disconnected groups.
- **Expand view** gives the diagram the available window area; Escape exits it. On narrow
  screens the table picker starts collapsed, except when manual selection is required. **Open table** opens the selected
  registered table's record list.

Keyboard users can move a focused table with arrow keys (Shift moves farther), expand
it with Enter/Space and activate junction labels with Enter/Space. Focus the canvas and
use +/− to zoom or 0 to fit. Selection, expansion, visibility and positions last only
while this page is open; reloading applies the initial selection policy again.

## Initial selection for large databases

For a database with many registered tables, open **Database schema**, search the table picker,
and select only the tables you want to explore. Above the default threshold of 100
available tables, the diagram opens empty with a message explaining this step. The
picker stays open even on narrow screens. Relationships appear as their tables are selected.

Configure this behavior when creating your existing authenticated admin:

```python
admin = Admin(
    auth=auth_backend, secret_key=session_secret, adapters=[adapter],
    schema_auto_limit=True,
    schema_table_limit=100,
)
```

`schema_auto_limit` defaults to `True`; `schema_table_limit` must be a positive integer.
The threshold counts registered tables visible to the current user after permission checks.
Exactly 100 tables still open selected by default. The setting changes initial selection
only: every authorized table remains searchable and **Show all** has no selection limit.
Set `schema_auto_limit=False` to select every available table immediately, or change
`schema_table_limit` for your database. Neither setting changes registration, permissions
or record operations. The full metadata catalog is still loaded; these settings do not
limit reflection or metadata transferred to the browser.

## Rendering large selections

**Show all** and `schema_auto_limit=False` keep every selected table available in the
canvas. Large selections use bounded routing work and update the moved card and its
incident links during dragging, without rebuilding every card. Pan and zoom keep the
existing diagram. Long foreign-key chains do not depend on the browser's recursion limit.

**Auto layout** folds large, stretched groups into compact columns and packs disconnected
components using the workspace's proportions. This keeps thousands of tables from forming
long sparse strips around an empty center. Card sizes still account for visible and expanded
fields; all selected tables remain present. Small diagrams retain their relationship layers.
Use **Fit schema** to fit existing positions without rearranging them, or **Auto layout**
to discard manual positions and recompute the arrangement for the current window size.

In dense selections, a link can cross an unrelated card when a clear detour would be
expensive to find. Select its source or target to highlight the relationship, or hide
unrelated tables in the picker for a clearer diagram. Smaller selections retain full
obstacle-avoiding routing.

The SQL reflection adapter reuses relationship metadata within its current reflected
snapshot. After database migrations, call `await adapter.refresh()` before reloading the
page to discover added or removed foreign keys and changed uniqueness constraints;
see [SQL reflection](integration.md). The cache contains physical metadata only; permissions
and field visibility are evaluated for each schema request.

## Permissions and field policy

The schema requires authentication and both `list` and `view` permission for each
table. Relationships to unavailable tables and links through hidden join fields
are omitted. Group choices and their counts include only these authorized tables;
groups with no available tables are absent. Field visibility follows `ModelOptions`, including the default exclusion of
credential fields. A restricted registered junction cannot reappear as a synthetic card.

An unregistered junction exposes only its adapter-supplied field metadata, with credential
fields excluded. It has no record-list link or CRUD operations. Register/configure the
junction as a table if it needs application-specific field restrictions.

The page uses the same theme tokens as lists and forms; see [interface customization](styling.md).
Its packaged JavaScript is allowed by a page-specific SHA-256 CSP hash and SRI. Custom
pages retain their existing script policy.

## Custom adapters

Existing `RelationAdapter.relations()` metadata is sufficient for basic links. Optional
`Relation.source_key_fields` and `target_key_fields` describe the actual join columns,
including alternate unique keys. `through` identifies an M:N junction; `junction` supplies
its fields and the foreign keys on each side:

```python
from quite_admin import Field, Junction, Relation

Relation(
    name="tags", target=Tag, kind="many_to_many",
    source_key_fields=("id",), target_key_fields=("id",), through="product_tags",
    junction=Junction(
        name="product_tags",
        fields=(
            Field("product_id", int, primary_key=True),
            Field("tag_id", int, primary_key=True),
        ),
        source_fields=("product_id",), target_fields=("tag_id",),
        model=ProductTag,  # optional: identifies a registered junction model
    ),
)
```

Junction metadata does not require a primary key. Optional sync/async
`schema_relations(model)` can provide diagram-specific metadata without changing the
relationships available for editing. Built-in SQLAlchemy discovery also includes physical
foreign keys without an ORM `relationship()`. Adapter API version 1 is unchanged.
