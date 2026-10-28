# Архитектура

```text
FastAPI mount ───┐
                ├── Admin ASGI / Starlette ── Jinja2 UI and custom pages
Litestar mount ─┘              │
                    Authentication / CSRF / permissions
                              │
                    ModelSchema / Field / Query
                              │
                       Adapter protocol
                    ┌────┬────┬─────┬────┐
               SQL Core  ORM  Tortoise  Peewee  Custom repositories
```

## Два режима доступа к данным

Общего протокола introspection/persistence у Python ORM нет. Через SQL reflection можно
получить физические таблицы и обеспечить CRUD независимо от ORM. Но в БД нет информации
о Python defaults, Enum-классах, model validators и application services.
Поэтому reflection и ORM adapters — разные явные варианты подключения.
Библиотека не обещает автоматически исполнить бизнес-правила, которых нет в источнике.

SQLAlchemy в `SQLAdapter` используется как SQL toolkit. `SQLAlchemyAdapter`, напротив,
работает через ORM Session и вызывает ORM persistence. Для soft delete, tenant isolation
и прикладных инвариантов точка интеграции — свой адаптер над application service.

## Контракты

- `ModelSchema`: имя коллекции, scalar fields, один или несколько primary key.
- `Field`: тип, nullable/default/generated/read-only, choices, foreign key metadata.
- `ModelOptions`: независимая от ORM политика отображения и записи.
- `Query`: уже проверенные pagination, sort и текстовый поиск.
- `RecordPage`: scalar mappings и общее количество.
- `Adapter`: discovery/introspection и пять CRUD-операций.
- `AuthBackend`: проверка credentials и повторная проверка identity.

Моделью в адаптере может быть ORM-класс, SQL Table или дескриптор внешнего repository.
Ядро не импортирует ни одну ORM. Неиспользуемые ORM не нужны при установке.

## Путь изменения записи

1. Проверить сессию и актуальность identity в backend приложения.
2. Разрешить действие коллекции (`edit`, `create`, `delete`).
3. Ограничить тело, разобрать form data, запретить дубликаты, проверить CSRF.
4. Сформировать серверный allowlist. Неизвестное / hidden / read-only отвергнуть.
5. Преобразовать строки в scalar types; ошибки вернуть в форму.
6. Выполнить операцию адаптера в отдельной транзакции.
7. Перевести constraint failure в `409`, откатить транзакцию; после успеха PRG redirect.

Identity хранится в cookie только как subject. Роли и актуальность пользователя
поступают из backend при каждом защищённом запросе. Ключи записей кодируются в
URL-safe base64 JSON-массив; значения типизируются при декодировании. Поддержаны UUID,
составные ключи и строки со слешами. Кодирование не заменяет проверку прав.

## Асинхронность и lifecycle

Синхронные SQLAlchemy/Peewee операции целиком выполняются в `anyio.to_thread.run_sync`.
Сессия/connection создаётся и закрывается в том же потоке. Нельзя разделять Session
между запросами. SQLAlchemy AsyncSession использует `run_sync` внутри greenlet bridge,
DB I/O остаётся async; Tortoise использует native async API.

Приложение владеет startup/shutdown, engine/pool и миграциями. Обнаружение моделей
происходит после startup, что существенно для Tortoise raw FK fields. Reflection кеширует
metadata и атомарно заменяет её при `refresh()`. Dashboard не выполняет `COUNT(*)`
для каждой таблицы: запросы записей начинаются при открытии списка.

## Точки расширения

- ORM / database: свой `Adapter`.
- Identity: свой `AuthBackend`.
- Коллекции и поля: `ModelOptions`, `FieldOptions`, `register()`, `configure()`.
- Layout / формы: Jinja loader с приоритетом пользовательского каталога.
- Отдельные экраны: `Page` + context callback + permission.

Права текущей версии — уровня коллекции. Tenant isolation должна быть частью адаптера.
Запись в reflection не запускает ORM hooks. GET не изменяет данные; удаление возможно
только POST после страницы подтверждения.

## Точки интеграции

FastAPI использует [ASGI sub-app mount](https://fastapi.tiangolo.com/advanced/sub-applications/),
Litestar — [ASGI mount handlers](https://docs.litestar.dev/main/usage/routing/overview.html#mounting-asgi-apps).
Обёртка приводит относительные нормализованные пути Litestar к Starlette `path/root_path`.
Это проверено тестами с вложенным router и proxy prefix.

SQLAlchemy использует [registry / runtime inspection](https://docs.sqlalchemy.org/en/20/orm/mapping_api.html)
и [MetaData.reflect](https://docs.sqlalchemy.org/en/20/core/reflection.html).
Tortoise предоставляет [model metadata](https://tortoise.github.io/models.html),
Peewee — [Model._meta](https://docs.peewee-orm.com/en/latest/peewee/models.html).

Текущий lock и SQLite matrix подтверждают установленные версии. PostgreSQL/MySQL
и отдельные dependency-version matrices — следующие полезные расширения CI.
