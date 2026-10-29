# GINO

`GinoAdapter` поддерживает существующие модели **GINO 1.0.x** в PostgreSQL через asyncpg.
Дополнительные модели админки и маппинги SQLAlchemy ORM не нужны. Один адаптер работает
с FastAPI и Litestar.

## Установка

```bash
pip install 'quite-admin[gino-legacy,fastapi]'
# Или: pip install 'quite-admin[gino-legacy,litestar]'
```

GINO 1.x требует SQLAlchemy 1.3, а адаптеры SQL reflection и SQLAlchemy — SQLAlchemy 2.x.
В приложении GINO выбирайте extra `gino-legacy` вместо `sqlalchemy` или `all`.
Существующий extra `all` сохраняет набор зависимостей современных адаптеров и не включает
GINO. См. [описание совместимости GINO](https://python-gino.org/docs/en/1.0/how-to/faq.html).

Нерелизное имя установки `quite-admin[gino]` заменено на `quite-admin[gino-legacy]`;
Python-импорт `quite_admin.adapters.gino.GinoAdapter` сохранён. Выпущенные версии GINO
требуют старый стек SQLAlchemy. Современные модели SQLAlchemy используют
[адаптер SQLAlchemy](integration.md), а модели GINO — этот адаптер.

## Подключение существующих моделей

```python
import os
from quite_admin import Admin, ModelOptions, PasswordAuth
from quite_admin.adapters.gino import GinoAdapter
from myapp.database import db
from myapp.models import User, Order  # Импортируйте модели до обнаружения.

adapter = GinoAdapter(db)
# Чтобы ограничить доступ: GinoAdapter(db, models=[User, Order])
admin = Admin(
    auth=PasswordAuth({"admin": os.environ["ADMIN_PASSWORD_HASH"]}),
    secret_key=os.environ["ADMIN_SESSION_SECRET"],
    adapters=[adapter],
)
admin.configure("users", options=ModelOptions(exclude=("password_hash",)))
admin.mount_fastapi(app)
# Или: admin.mount_litestar(app)
```

`db` — существующий экземпляр `gino.Gino` приложения. Автоматически обнаруживаются
импортированные конкретные подклассы его `db.Model`, включая наследников абстрактных
баз проекта. Модели других экземпляров не сканируются. Без `models` работает обнаружение;
`models=[]` явно отключает доступ ко всем моделям. Каждой модели нужен первичный ключ.
В настройках полей и словарях записей используются имена атрибутов модели, в том числе
когда имя атрибута отличается от имени колонки в БД.

Пул открывает и закрывает приложение в собственном lifespan. Существующий lifespan
нужно сохранить; для нового приложения FastAPI используется следующий подход:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def database_lifespan(app):
    async with db.with_bind(os.environ["DATABASE_URL"]):
        yield

app = FastAPI(lifespan=database_lifespan)
admin.mount_fastapi(app)
```

Для Litestar используйте `Litestar(lifespan=[database_lifespan])` и подключите к нему
админку. Импортируйте `quite_admin.adapters.gino` до открытия пула: модуль регистрирует
родной диалект asyncpg GINO через публичный реестр SQLAlchemy, обходя зависимость старого
загрузчика entry points SQLAlchemy 1.3 от `pkg_resources`. Адаптер не открывает пул,
не создаёт таблицы, не запускает миграции и не закрывает движок приложения.

## Запросы, запись и связи

CRUD, поиск буквального текста, стабильная пагинация, сортировка, типизированные фильтры
и выбор колонок соответствуют [общему контракту адаптеров](custom-adapters.md).
Поддерживаются полные составные ключи, UUID, Decimal, enum, даты и время, JSON/JSONB
и 64-битные целые числа. Вычисляемые колонки доступны только для чтения.

Из метаданных внешних ключей обнаруживаются прямые и обратные связи 1:N, а из уникальных
внешних ключей — 1:1. Чистые промежуточные таблицы с двумя ограничениями внешних ключей
и уникальной совокупной идентичностью дают редакторы M:N. Составные внешние ключи
поддерживаются. Имена связей соответствуют соглашению SQL reflection; получить их можно
через `adapter.relations(Model)`. Показываются только связи с обнаруженными моделями.
Промежуточные таблицы с дополнительными данными не становятся редакторами M:N —
редактируйте такую модель отдельно. Свойства загрузчиков и связи только в Python
без внешних ключей БД автоматически не определяются.

Каждая запись выполняется в отдельной транзакции с rollback при любой ошибке. Поля
и связи сохраняются атомарно; обязательные связи нельзя отсоединять, отсоединение
не удаляет связанные записи, нарушения ограничений превращаются в `Conflict`.
Чтение получает и освобождает соединение без commit транзакции записи. Внешняя
транзакция приложения не переиспользуется и не фиксируется адаптером.

Создание, обновление и удаление записей вызывают родные методы сохранения GINO.
Применяются Python defaults колонок, ограничения, триггеры и каскады БД.
У GINO нет сессии SQLAlchemy ORM, поэтому события SQLAlchemy ORM не выполняются.
Изменения промежуточной таблицы M:N выполняются SQL-запросами. Сервисы приложения,
свои загрузчики, JSON-свойства и soft-delete автоматически не подключаются.
Для записи через сервисы используйте [DelegatingAdapter и lifecycle hooks](extensions.md);
при необходимости явно реализуйте атомарный `save_relations`.

Для UUID в GINO 1.0.1 используйте PostgreSQL-тип `UUID()` с настройкой по умолчанию
`as_uuid=False`: asyncpg уже возвращает Python UUID. Объявление `UUID(as_uuid=True)`
вызывает ошибку двойного преобразования в SQLAlchemy 1.3; адаптер не меняет типы
колонок приложения и кодеки драйвера.

## Проверки с PostgreSQL

Для GINO предусмотрены отдельное locked-окружение и PostgreSQL CI job для CPython 3.11–3.15.
Обычный SQLite-набор не устанавливает GINO вместе с SQLAlchemy 2.x.

```bash
UV_PROJECT_ENVIRONMENT=.venv-gino-legacy uv sync --locked --no-dev --extra gino-legacy --group gino-check
QUITE_ADMIN_GINO_TEST_DATABASE_URL='postgresql://quite_admin:local-test-password@127.0.0.1:55432/quite_admin_gino_test' \
  UV_PROJECT_ENVIRONMENT=.venv-gino-legacy uv run --no-sync pytest --confcutdir=tests/gino tests/gino -q
```

Используйте **одноразовую** локальную БД `quite_admin_gino_test` (или `quite_admin_test`).
Каждый тест создаёт и удаляет изолированную схему. Fixture отклоняет другие имена БД
и внешние адреса. Контрактные тесты общие с современными адаптерами; дополнительные
проверяют типы PostgreSQL, составные связи, родные хуки, каскады и изоляцию транзакций.
