# List filters

Open **Filters** above a table, set the conditions and press **Apply filters**.
All conditions combine with AND and run in the database before counting or pagination.
Active chips show every condition; × removes one, **Clear all** resets filters and search
while preserving sorting and page size. Search, sorting and page links retain active filters.
The resulting URL can be bookmarked or shared with another authorized user.

| Field | Control |
|---|---|
| Boolean, enum, choices | Any value or one exact value |
| Integer, Decimal, float, date, time, datetime | Inclusive From / To bounds; either can be omitted |
| String, UUID | Exact value; use the main search for substring matches |
| Nullable field | Is NULL / Is not NULL, separately from the scalar condition |
| JSON, binary, unsupported | NULL condition only, when nullable |

NULL means SQL NULL, not an empty string or JSON null. A blank control adds no condition.
Datetime/time inputs accept ISO values; timezone handling and string comparison follow
the database's column types and collation. Decimal values are parsed without converting
them through JavaScript numbers. Invalid values and reversed ranges keep the controls
and show errors with HTTP 422. Unknown, hidden or duplicate filter parameters return 400.

## Choose fields

```python
from quite_admin import ModelOptions

admin.configure("products", options=ModelOptions(
    filter_fields=("active", "category", "price", "stock"),
    search_fields=("name",),
))
```

`filter_fields=None` exposes supported visible scalar fields; `()` disables scalar
filter controls. The configured order is preserved. Excluded and automatically hidden
sensitive fields remain unavailable even when named in `filter_fields`. Read-only fields
can be filtered. Field labels and choices use the normal `FieldOptions` overrides.
At most 50 scalar conditions and 10 relationship conditions may be active.

## Related records

Registered relationships appear alongside scalar filters when the adapter supports
`Query.related`. Use **Choose records** to search the target collection and select one
existing record. The list then includes records linked to that target: 1:1, N:1, 1:N
and M:N are supported. Multiple different relationships combine with AND.

Both ends must be registered with the same adapter. Parent list permission and target
list/view permission are required; edit permission is unnecessary. Relationship and
field visibility rules still apply. `ModelOptions.relations` controls which relations
appear. Every lookup request repeats these permission checks. The shared picker uses
an integrity-checked script under the same narrow CSP as [relationship forms](relationships.md).

## Adapter queries

```python
from decimal import Decimal
from quite_admin import Filter, Query, RelatedFilter

page = await adapter.list(Product, Query(
    filters=(Filter("active", "eq", True), Filter("price", "gte", Decimal("10.00"))),
    related=(RelatedFilter("tags", {"id": 17}),),
    limit=25,
))
```

The relation name comes from `adapter.relations(Product)`, not a raw SQL expression.
Target keys use their Python types, including UUID and composite keys. Custom adapters
opt in explicitly; see [the optional capability contract](custom-adapters.md#relationship-filters).
