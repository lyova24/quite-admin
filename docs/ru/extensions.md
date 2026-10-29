# Операции и расширения

`Field`, `ModelSchema`, `Query`, `Relation` описывают данные независимо от HTML.
Контролы настраиваются через `FieldOptions`; для новых экранов есть
[страницы и шаблоны](custom-pages.md), для бизнес-правил — [сервисный адаптер](custom-adapters.md).

## Lifecycle записи

1. Перепроверить identity и право на операцию коллекции.
2. Проверить CSRF, allowlist, типы полей и выбор связанных записей.
3. Вызвать `OperationHooks.before_write` со снимком операции.
4. Выполнить атомарную запись адаптера/сервиса с rollback при ошибке.
5. После commit вызвать `after_write`, записать безопасные метаданные и перенаправить.

```python
from quite_admin import OperationHooks, current_operation
from quite_admin.errors import ValidationError

async def validate(operation):
    if operation.values.get("stock", 0) < 0:
        raise ValidationError({"stock": "Остаток не может быть отрицательным."})

async def notify(operation, saved):
    await notifications.admin_change(operation.collection, operation.action)

admin = Admin(
    auth=auth_backend, secret_key=session_secret,
    hooks=OperationHooks(before_write=validate, after_write=notify),
)
```

Хуки бывают sync/async; sync-хуки не должны выполнять блокирующий I/O. Они работают
для create, edit со связями, delete и пользовательских действий. `Operation` содержит
request, актуальную identity, коллекцию, модель, action, типизированный ключ, значения,
ключи связей и предыдущую запись. Mappings скопированы и неизменяемы на верхнем уровне;
изменение вложенного снимка не меняет данные предстоящей записи. Для преобразования
значений используйте parser поля или сервис.

`current_operation()` доступен в сервисах и ORM-хуках, включая worker синхронного
адаптера. Вне записи он возвращает `None`, контекст сбрасывается и при ошибке.
Не сохраняйте request/operation за пределами времени жизни запроса.

Before-хук выполняется **вне** транзакции адаптера и может видеть устаревшую запись.
Критичные инварианты и права на строку проверяются внутри транзакции сервиса.
After-хук — уведомление: при ошибке пишется `quite_admin.after_write_failed` без значений
и текста исключения; уже сохранённая запись не превращается в ошибку ответа. Для
надёжного аудита сохраняйте audit row/outbox внутри транзакции сервиса. Встроенного
durable audit store нет.

## Действия записи

```python
from quite_admin import ModelOptions, RecordAction

async def publish(operation):
    return await products.publish(operation.key, actor=operation.identity.subject)

admin.configure("products", options=ModelOptions(
    actions=(RecordAction("publish", "Опубликовать", publish),),
))
```

Кнопки появляются на единой странице сущности. Выполнение требует POST, сессию,
CSRF и по умолчанию право `edit`. Для разрушительного действия задайте
`required_permission="delete"`; дополнительный callback задаётся через `permission`.
Handler принимает `Operation`, управляет своей транзакцией и возвращает scalar mapping
или `None`; после него выполняется переход к текущей записи. Действия, удаляющие
запись, требуют собственного подтверждения и перехода в приложении. GET действия
не выполняет. Handler может выбрасывать публичные ошибки адаптера. Подпись действия
задаётся на языке настроенного интерфейса.

Совместимость определяют `ADAPTER_API_VERSION` и [контракт адаптера](custom-adapters.md).
Изменения шаблонов и безопасных defaults перечислены в `CHANGELOG.md` для перехода на 0.2.0.
