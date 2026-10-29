# Support another ORM

Implement `quite_admin.adapters.base.Adapter` for an ORM, a document database or an
application repository. No inheritance from a library class is required.

```python
class MyAdapter:
    def discover(self): ...                         # Iterable of existing models; may be async
    def describe(self, model): ...                  # ModelSchema containing Field metadata
    async def list(self, model, query): ...          # RecordPage
    async def get(self, model, key): ...             # dict | None
    async def create(self, model, values): ...       # dict
    async def update(self, model, key, values): ...  # dict
    async def delete(self, model, key): ...          # None
```

## Return scalar data

`describe()` returns a `ModelSchema` and `Field` metadata, not a duplicate ORM or DTO model.
CRUD operations return scalar mappings instead of objects with lazy relationships.
`key` is a dictionary, which supports composite primary keys.

`Query` contains pagination, sorting, text search, typed AND filters and optional
scalar-column projection. Call `query.validate(schema)` before data access.
`RecordPage` contains records and the total matching count.
Discovery may be asynchronous if it performs I/O; synchronous discovery should only inspect metadata.

## Own the persistence rules

An adapter owns transactions, rollback, model-level validation, tenant scopes and session lifecycle.
Run a complete synchronous unit of work in one worker thread.
Never share an ORM session between requests.

Translate expected failures into `Conflict`, `NotFound` or `ValidationError` from
`quite_admin.errors`. The core handles authentication, CSRF, operation permissions,
field allowlists, scalar conversion and rendering.

For soft-delete rules, tenant isolation or service-layer invariants, an adapter that calls
your application service is the appropriate integration point.

## Register the adapter

```python
admin.add_adapter(my_adapter)
# Or disable discovery and register selected existing models:
# admin.add_adapter(my_adapter, discover=False)
# admin.register(User, adapter=my_adapter)
```

The source checkout contains a dependency-free adapter example in `tests/test_integration.py`.
See [architecture](architecture.md) for the request and transaction boundaries.

## Filters and columns

```python
from decimal import Decimal
from quite_admin import Filter, Query

query = Query(
    filters=(Filter("active", "eq", True), Filter("price", "gte", Decimal("10.00"))),
    order_by="price", columns=("id", "name", "price"), limit=25,
)
result = await adapter.list(Product, query)
```

Values use the field's Python type, including UUID, date and enum objects. Operators:
`eq`, `lt`, `lte`, `gt`, `gte`, `in`, `is_null`. Up to 50 filters combine with AND;
`in` accepts up to 1,000 values, and an empty sequence matches nothing. For NULL use
`Filter("note", "is_null", True)`. JSON/binary/unknown fields support only `is_null`.
No raw SQL or arbitrary lookup operators are accepted.

`total` counts matches before pagination. Sorting appends primary-key tie breakers.
Projection returns exactly the requested scalar keys; include PK fields when records
must remain addressable. It does not guarantee that an ORM loads only these columns.
Relationship queries follow the same contract. The HTML list does not expose a
filter-expression or projection query language.

## Application services

`DelegatingAdapter` reuses discovery, metadata and reads. Override every write that
needs business rules:

```python
from quite_admin import DelegatingAdapter

class ProductAdminAdapter(DelegatingAdapter):
    def __init__(self, reader, service):
        super().__init__(reader)
        self.service = service

    async def create(self, model, values):
        return await self.service.create_product(values)

    async def update(self, model, key, values):
        return await self.service.update_product(key, values)

    async def delete(self, model, key):
        await self.service.delete_product(key)

adapter = ProductAdminAdapter(native_adapter, product_service)
admin.add_adapter(adapter, discover=False)
admin.register(Product, adapter=adapter)
```

The service owns validation, transactions and rollback, returns scalar mappings and can
raise public adapter errors. Unoverridden writes still use the delegate. Register the
wrapper instead of discovering the same models again through the native adapter.
Optional `RelationAdapter` methods are **not** forwarded automatically: that could bypass
the overridden `update()`. Implement all three explicitly when the service can save
fields and relationships atomically.

## Compatibility contract

`ADAPTER_API_VERSION` is `1`. Structural adapters need no version attribute or base class.
Required protocol methods stay separate from optional relationship support. Changing
required methods/signatures requires a protocol version change and a documented breaking
package release. Before 1.0, breaking changes increase the package MINOR version.

The common suite is `tests/test_adapters.py`, `tests/test_adapter_safety.py` and
`tests/test_relations.py`. It runs across six adapter modes and the dedicated server
matrix. See [actual verification and limits](data-safety.md).
