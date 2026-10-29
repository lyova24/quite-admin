# Подключение и адаптеры

Админка монтируется как отдельное ASGI-приложение. Приложение владеет engine, сессиями и lifespan.

## Без привязки к ORM: SQL reflection

Установка из исходников:

```bash
pip install -e '.[sqlalchemy,fastapi]'
```

```python
import os
from fastapi import FastAPI
from sqlalchemy import create_engine
from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters.sql import SQLAdapter

engine = create_engine(os.environ["DATABASE_URL"])
admin = Admin(
    secret_key=os.environ["ADMIN_SESSION_SECRET"],  # минимум 32 случайных байта
    auth=PasswordAuth({"admin": os.environ["ADMIN_PASSWORD_HASH"]}),
    adapters=[SQLAdapter(engine, include_tables=("users", "orders"))],
)
admin.configure("users", options=ModelOptions(
    exclude=("password_hash",), readonly_fields=("created_at",),
))

app = FastAPI()
admin.mount_fastapi(app, "/admin")
```

Без `include_tables` обнаруживаются все таблицы выбранной схемы; `exclude_tables`
позволяет исключить служебные таблицы. Библиотека не создаёт таблицы и не запускает миграции.
Все доступные таблицы должны иметь primary key. Схема лениво отражается при первом
авторизованном запросе и кешируется; после миграции можно вызвать `await adapter.refresh()`.
Доступны `Engine` и `AsyncEngine`, параметр `schema` для схем БД.

MySQL [хранит `BOOLEAN` как `TINYINT(1)`](https://dev.mysql.com/doc/refman/8.4/en/numeric-type-syntax.html).
Reflection не различает его и обычный `TINYINT(1)`, поэтому целочисленные
колонки по умолчанию остаются числами. Для неоднозначных колонок можно явно указать
тип SQLAlchemy: он определяет разбор значений, типизированные фильтры и возвращаемые значения:

```python
from sqlalchemy import Boolean

adapter = SQLAdapter(engine, column_types={"users": {"active": Boolean()}})
```

Для именованной схемы используйте полный ключ таблицы, например `app.users`. Переопределения
должны ссылаться на обнаруженные таблицы и колонки и содержать экземпляры типов SQLAlchemy.
`refresh()` применяет их повторно. ORM-адаптеры сохраняют объявленные типы Boolean.

Этот режим выполняет SQL напрямую. Работают **DB constraints, server defaults и триггеры**.
Python defaults, ORM events, model validators, service-layer permissions и soft-delete
логика автоматически не выполняются. Если они необходимы, используйте ORM-адаптер
или свой адаптер, который вызывает application service.

## Существующие SQLAlchemy / SQLModel модели

```python
from sqlalchemy.orm import sessionmaker
from quite_admin import Admin
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from myapp.database import engine, Base

adapter = SQLAlchemyAdapter(sessionmaker(engine), base=Base)
admin = Admin(auth=auth_backend, secret_key=session_secret, adapters=[adapter])
admin.mount_fastapi(app)
```

Все импортированные модели из `Base.registry` обнаруживаются автоматически.
Для SQLModel передайте `base=SQLModel`. Дополнительные схемы описывать не нужно.
Асинхронные сессии:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker
adapter = SQLAlchemyAdapter(async_sessionmaker(async_engine), base=Base)
```

Для нестандартного callable, возвращающего `AsyncSession`, укажите `async_mode=True`.
Нужна **фабрика новых сессий**, не глобальная сессия и не FastAPI dependency generator.
Одна операция — одна сессия; синхронные запросы выполняются в worker thread.
Движком, connection pool и startup/shutdown управляет приложение.

## Litestar

```python
from litestar import Litestar
app = Litestar(route_handlers=[admin.litestar_route("/admin")])
# Или для уже созданного приложения: admin.mount_litestar(app, "/admin")
```

Работают вложенные routers, mount-пути и ASGI `root_path` для reverse proxy.
Админка является отдельным ASGI-приложением.

## Tortoise и Peewee

```python
from quite_admin.adapters.tortoise import TortoiseAdapter

# Tortoise.init() выполняется в lifespan основного приложения.
# Обнаружение произойдёт после startup, при первом запросе.
adapter = TortoiseAdapter(apps=("models",))
```

```python
from quite_admin.adapters.peewee import PeeweeAdapter
adapter = PeeweeAdapter(base=ProjectBaseModel)
# Или PeeweeAdapter(models=[User, Order])
```

Для Peewee используйте файловую SQLite или серверную БД: обычная `:memory:`
не разделяется между потоками. Подключение и транзакция создаются и закрываются
в одном worker thread. Tortoise выполняет запросы асинхронно через соединение модели.

Общие [настройки коллекций](configuration.md) работают с любым адаптером. Для другой ORM реализуйте [Adapter](custom-adapters.md).
