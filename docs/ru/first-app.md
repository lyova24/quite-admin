# Ваша первая админка

Запустите настоящее FastAPI-приложение с тремя связанными моделями SQLAlchemy:
**Customers → Orders → Order items**. В нём можно войти, менять записи, редактировать
связи и смотреть сохранённые изменения. Всё работает локально с вымышленными данными в SQLite.

Приложение уже есть? [Подключите существующие модели](quickstart.md).
Для знакомства с интерфейсом [откройте браузерное демо](https://lyova24.github.io/quite-admin/demo/)
с логином и паролем `admin` / `admin`.

## Скачать и запустить

Нужны CPython **3.11–3.15** и [uv](https://docs.astral.sh/uv/getting-started/installation/)
либо pip. Скачайте один файл [quickstart.py](https://raw.githubusercontent.com/lyova24/quite-admin/master/examples/quickstart.py)
в пустой каталог. Клонировать репозиторий и устанавливать Node.js не требуется.

При запуске через uv заголовок скрипта установит quite-admin, FastAPI, SQLAlchemy и Uvicorn
в отдельное окружение:

```bash
curl -fsSLo quickstart.py https://raw.githubusercontent.com/lyova24/quite-admin/master/examples/quickstart.py
QUITE_ADMIN_PASSWORD='local-demo-only' uv run --script quickstart.py
```

Другой вариант — активировать своё виртуальное окружение Python и использовать pip:

```bash
pip install 'quite-admin[sqlalchemy,fastapi]>=0.8.17,<0.9' 'uvicorn>=0.30,<1'
QUITE_ADMIN_PASSWORD='local-demo-only' python quickstart.py
```

Откройте [localhost:8000/admin/](http://localhost:8000/admin/). Логин — **admin**,
пароль — **local-demo-only**. Сервер слушает `127.0.0.1`.

## Пройти полный сценарий

1. Откройте **Orders**, затем **Starter order**. Измените **Status** с `pending` на `paid` и сохраните.
2. Откройте заказ снова. В редакторе связи **Customer** выберите **Sam Lee** и сохраните.
3. Откройте **Order Items → Notebook**. Измените **Quantity** с `2` на `3` и сохраните.
4. Откройте **Activity history**. Раскройте изменения: будут видны пользователь и значения до/после.
5. В **Customers** создайте клиента, измените его и удалите через страницу подтверждения.
6. Откройте **Database schema**: на схеме будут те же три модели и их связи.

Изменения сохраняются после перезапуска сервера. Начальные записи добавляются только
при пустой таблице Customers. Для упражнения с созданием и удалением используйте
отдельные пробные записи: исходные клиенты и заказы связаны внешними ключами БД.
В примере заказ может быть без клиента, поэтому эта связь допускает NULL.
Текущий адаптер запрещает замену обязательной связи; для упражнения с выбором
другого клиента используется необязательная связь.

## Как модели превращаются в админку

[Полный исходник](https://github.com/lyova24/quite-admin/blob/master/examples/quickstart.py)
содержит обычные модели SQLAlchemy и lifespan FastAPI, который готовит учебную базу.
Внутри `create_app()` админка подключается так:

```python
admin = Admin(
    title="Orders back office",
    auth=PasswordAuth.single_user("admin", password),
    secret_key=os.getenv("QUITE_ADMIN_SECRET", secrets.token_urlsafe(48)),
    adapters=[SQLAlchemyAdapter(sessions, base=Base)],
    storage=data_dir / "history.sqlite3",
    secure_cookies=False,  # This example serves local HTTP only.
)
admin.mount_fastapi(app)
```

`base=Base` обнаруживает все три модели. Типы колонок задают формы, а связи SQLAlchemy —
редакторы связанных записей. Отдельные admin-классы, DTO и Pydantic-схемы не нужны.
Позже можно [настроить таблицы и поля](configuration.md), не заменяя модели.

## Локальные файлы и сессии

Пример пишет только в `.quite-admin/quickstart/` рядом со скачанным скриптом:

| Файл | Содержимое |
| --- | --- |
| `shop.db` | Три таблицы моделей и ваши вымышленные записи |
| `history.sqlite3` | Служебные данные админки и история действий |

Остановить сервер можно через Ctrl+C. При каждом запуске создаётся новый случайный
секрет сессии, поэтому потребуется войти снова. Чтобы сессии переживали перезапуск,
задайте `QUITE_ADMIN_SECRET`: постоянное случайное значение длиной не менее 32 байт.
Чтобы начать с чистых данных, остановите сервер и переместите каталог примера
`.quite-admin/quickstart/` в другое место.

## Подключить своё приложение

[Добавьте quite-admin в существующее приложение](quickstart.md), передав свои base и фабрику сессий.
Для Litestar используйте `admin.mount_litestar(app)`; модели и настройка адаптера остаются теми же.
Другие ORM и SQL reflection описаны в [интеграциях](integration.md).

В примере один локальный аккаунт и cookies для HTTP. Для развёртывания приложения
пройдите [руководство по развёртыванию](deployment.md), проверьте [гарантии API](api-stability.md)
и [матрицу совместимости БД](data-safety.md).
