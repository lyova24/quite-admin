# Подключение за две минуты

Нужны CPython **3.11–3.15**, существующее приложение, база и модели.
Опубликованного релиза пока нет; установите этот checkout в окружение приложения:

```bash
pip install '/path/to/quite-admin[sqlalchemy,fastapi]'
# Для Litestar: pip install '/path/to/quite-admin[sqlalchemy,litestar]'
```

## Существующее FastAPI-приложение

Добавьте код рядом с созданием `app`. Замените импорт на свои существующие
SQLAlchemy/SQLModel base и фабрику сессий:

```python
import os
from quite_admin import Admin, PasswordAuth
from quite_admin.adapters.sqlalchemy import SQLAlchemyAdapter
from myapp.database import Base, SessionFactory

admin = Admin(
    auth=PasswordAuth.single_user('admin', os.environ['QUITE_ADMIN_PASSWORD']),
    secret_key=os.environ['QUITE_ADMIN_SECRET'],
    adapters=[SQLAlchemyAdapter(SessionFactory, base=Base)],
    secure_cookies=False,  # Локальный HTTP; в production с HTTPS используйте True.
)
admin.mount_fastapi(app)
```

В конфигурации приложения задайте `QUITE_ADMIN_PASSWORD` и постоянный случайный
`QUITE_ADMIN_SECRET` длиной не менее 32 байт. Импортируйте модули моделей до startup.
Запустите приложение как обычно и откройте `/admin/`; логин — `admin`, пароль из
настройки. Дополнительные схемы и классы admin-моделей не нужны. Lifespan базы
и миграции остаются под управлением приложения.

## Существующее Litestar-приложение

Используйте тот же `Admin`, заменив вызов mount:

```python
admin.mount_litestar(app)
```

Подключайте до запуска приложения. Для Tortoise выполните инициализацию в lifespan
до обнаружения моделей и выберите `TortoiseAdapter`. Все адаптеры, вложенные пути
и прокси описаны в [подключении](integration.md).

## Любая ORM через её базу

Для обнаружения физических таблиц передайте engine существующей базы:

```python
from quite_admin.adapters.sql import SQLAdapter
adapter = SQLAdapter(engine)
```

Укажите `adapters=[adapter]` в `Admin`. Reflection выполняет правила и триггеры БД;
для Python-хуков и бизнес-правил нужен нативный или сервисный адаптер. Перед
открытием коллекций проверьте [защиту секретных и служебных полей](configuration.md)
и [матрицу СУБД](data-safety.md).

## Интерфейс

![Список записей](../assets/screenshots/products.png)

Одна страница содержит поля и редакторы связей. На примере read-only видно ту же
страницу с защищённой датой регистрации.

![Единая страница записи](../assets/screenshots/record.png)

![Связи в той же форме](../assets/screenshots/relationships.png)

![Настройка полей только для чтения](../assets/screenshots/fields.png)

[Посмотреть 12-секундный обзор (MP4)](../assets/walkthrough.mp4).

## Запуск готового примера

```bash
uv sync --locked --python 3.15
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.fastapi_app:app --reload
# Либо examples.litestar_app:app.
```

Откройте [localhost:8000/admin/](http://localhost:8000/admin/), войдите с
`admin` / `local-demo-only`. Пример создаёт отдельную SQLite-базу; путь задаётся
через `QUITE_ADMIN_DEMO_DB`. Для стабильной Python 3.15 нужен uv 0.13.6+.
Самой библиотеке Node.js не нужен — он используется только при сборке документации.

## Дальше

Попробуйте [фильтры списков](filters.md), [поиск связанных записей](relationships.md)
и [интерактивную схему БД](database-schema.md). Перед открытием админки настройте
[авторизацию и права](authentication.md), затем адаптируйте [палитру, плотность и шаблоны](styling.md)
под своё приложение.
