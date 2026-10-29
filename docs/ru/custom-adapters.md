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

## Фильтры и колонки

Перед запросом вызывайте `query.validate(schema)`.

```python
from decimal import Decimal
from quite_admin import Filter, Query

query = Query(
    filters=(Filter("active", "eq", True), Filter("price", "gte", Decimal("10.00"))),
    order_by="price", columns=("id", "name", "price"), limit=25,
)
result = await adapter.list(Product, query)
```

Значения имеют Python-тип поля, включая UUID, date и enum. Операторы: `eq`, `lt`,
`lte`, `gt`, `gte`, `in`, `is_null`. До 50 фильтров объединяются AND. `in` принимает
до 1000 значений; пустая последовательность не находит ничего. Для NULL используйте
`Filter("note", "is_null", True)`. JSON/binary/неизвестные типы допускают только
`is_null`. Произвольный SQL и lookup-операторы не принимаются.

`total` считает совпадения до пагинации. Сортировка добавляет PK для стабильного порядка.
Проекция возвращает только указанные скалярные ключи; включайте PK, если запись должна
оставаться адресуемой. Она не гарантирует загрузку ORM только этих колонок. Запросы
связей используют тот же контракт. HTML-список не предоставляет язык фильтров и проекций.

## Сервисы приложения

`DelegatingAdapter` повторно использует обнаружение, метаданные и чтение. Переопределите
каждую операцию записи, которой нужны бизнес-правила:

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

Сервис отвечает за проверки, транзакцию и rollback, возвращает скалярные mappings
и может выбрасывать публичные ошибки адаптера. Непереопределённые записи вызывает
delegate. Регистрируйте обёртку вместо повторного обнаружения тех же моделей нативным
адаптером. Методы `RelationAdapter` автоматически **не** делегируются: это могло бы обойти
переопределённый `update()`. Реализуйте все три явно, когда сервис умеет атомарно
сохранять поля и связи.

## Совместимость контракта

`ADAPTER_API_VERSION` равен `1`. Стороннему адаптеру не нужны атрибут версии или базовый
класс. Обязательный протокол отделён от необязательной поддержки связей. Изменение
обязательных методов требует новой версии протокола и описанного breaking release.
До 1.0 такие изменения поднимают MINOR пакета.

Общий набор — `tests/test_adapters.py`, `tests/test_adapter_safety.py` и
`tests/test_relations.py`: шесть режимов адаптеров и отдельная матрица серверов.
См. [подтверждённые проверки и ограничения](data-safety.md).
