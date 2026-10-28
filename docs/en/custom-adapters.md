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

`Query` contains validated pagination, sorting and text-search settings.
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
