# Другая ORM

Реализуйте контракт `quite_admin.adapters.base.Adapter`:

```python
class MyAdapter:
    def discover(self): ...                         # Iterable[existing model], можно async
    def describe(self, model): ...                  # ModelSchema с Field, не ORM/DTO-модель
    async def list(self, model, query): ...          # RecordPage
    async def get(self, model, key): ...             # dict | None
    async def create(self, model, values): ...       # dict
    async def update(self, model, key, values): ...  # dict
    async def delete(self, model, key): ...          # None
```

Результаты — скалярные mappings, без lazy ORM-объектов. `key` — словарь,
поэтому поддерживаются составные ключи. Адаптер отвечает за транзакции,
rollback, model-level проверки, tenant scopes и lifecycle своих сессий.
Ожидаемые ошибки переводите в `Conflict`, `NotFound`, `ValidationError` из
`quite_admin.errors`. Ядро отвечает за авторизацию, CSRF, allowlist полей, преобразование
типов и отображение. Пример стороннего адаптера находится в `tests/test_integration.py` исходного репозитория.
