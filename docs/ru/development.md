# Разработка и совместимость

## Python

Поддерживаются CPython 3.11–3.15. CI запускает полный SQLite-набор тестов для каждой версии без `continue-on-error`.

Локально проверены Python 3.14.7 и 3.15.2. Нет отдельных гарантий для free-threaded сборок и альтернативных реализаций Python.

Диапазон зависимостей допускает Starlette 0.x и 1.x. В lock-файле выбран Starlette 1.10.0,
чей `TestClient` использует `anyio.from_thread.BlockingPortal` и `httpx2`.
Оба HTTP-клиента входят в зависимости для разработки: синхронные тесты примеров используют
`TestClient` Starlette, асинхронные интеграционные тесты — `httpx.ASGITransport`.
Pytest считает `DeprecationWarning` ошибкой, чтобы обнаруживать устаревшие API в проверяемом наборе зависимостей.

## Проверка кода

```bash
uv run pytest -q
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv build
```

Интеграционные тесты проходят CRUD на SQLite для sync/async SQL reflection,
sync/async SQLAlchemy, Tortoise и Peewee под FastAPI и Litestar. Проверяются
CSRF, mass assignment, read-only поля, XSS, права, rollback, шаблоны и proxy prefixes.
PostgreSQL/MySQL используют соответствующие драйверы адаптеров, но в этом репозитории
пока не проверяются интеграционными тестами.

Это первая рабочая версия библиотеки. Пока нет relation pickers / many-to-many editor,
загрузки файлов, bulk actions, audit log, row-level permission API и защиты от
конкурирующего редактирования в UI (действует last-write-wins). Свои страницы пока GET-only.
Reflection не восстанавливает логические типы, потерянные в схеме: UUID в SQLite
может оказаться строкой, а enum — обычным VARCHAR. Для сохранения типов используйте
ORM-адаптер. Автообнаружение требует импортированных моделей и не импортирует весь проект.


## Документация Diplodoc

Исходный язык — английский (`docs/en`), перевод — русский (`docs/ru`). Структура страниц и `toc.yaml` совпадает.

Требования: Node.js 24+ и npm 11.5.1+. Из корня репозитория:

```bash
npm ci
npm run docs:build
npm run docs:serve
```

Сборка появляется в `build/docs`. Откройте [localhost:8001](http://localhost:8001/): корневой URL ведёт в английскую версию. Русская версия доступна по `/ru/`. Сборка проверяет состав переводов, ссылки и предупреждения Diplodoc. CI сохраняет HTML как artifact и не публикует сайт автоматически.

Новые страницы добавляйте в обе языковые папки и оба `toc.yaml`. Меняйте примеры API синхронно. Настройки находятся в `docs/.yfm`, версия CLI закреплена в `package-lock.json`.
