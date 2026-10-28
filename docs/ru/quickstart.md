# Быстрый старт

Поддерживаются CPython 3.11, 3.12, 3.13, 3.14 и 3.15. Для демо нужен uv.

```bash
cd quite-admin
uv sync --locked
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.fastapi_app:app --reload
```

Открыть [localhost:8000/admin/](http://localhost:8000/admin/).
Логин: `admin`, пароль: `local-demo-only`. Это пример для локальной разработки:
SQLite с демонстрационными данными создаётся автоматически, cookie разрешены по HTTP.
Секрет сессии генерируется на запуск, если не задан `QUITE_ADMIN_SECRET`.

Тот же пример на Litestar:

```bash
QUITE_ADMIN_PASSWORD='local-demo-only' uv run uvicorn examples.litestar_app:app --reload
```

## Своё приложение

Установите пакет из исходников с нужными extras:

```bash
pip install -e '.[sqlalchemy,fastapi]'
# Или: pip install -e '.[tortoise,litestar]'
```

Далее выберите [SQL reflection или ORM-адаптер](integration.md). Драйвер БД устанавливается отдельно, если он не входит в зависимости ORM.

## Python 3.14 и 3.15

```bash
uv sync --locked --python 3.14
uv sync --locked --python 3.15
```

Используйте uv 0.13.6 или новее для актуального каталога стабильных Python. Обычные сборки CPython проходят полный набор тестов; free-threaded сборки отдельно не проверяются.
