# Разработка и совместимость

Планируемая версия библиотеки — **0.2.0**. Изменения относительно 0.1.0 описаны в
`CHANGELOG.md` репозитория. Повышение MINOR учитывает редактирование связей, единую
страницу записи и новые настройки интерфейса. Обновление версии не публикует релиз.

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
теперь имеют отдельные [контрактные CI jobs](data-safety.md).
PostgreSQL 17 также проверен локально; локальный запуск MySQL 8.4 ждёт доступности образа.

Это первая рабочая версия библиотеки. Пока нет загрузки файлов, bulk actions, audit log,
row-level permission API и защиты от
конкурирующего редактирования в UI (действует last-write-wins). Свои страницы пока GET-only.
Reflection не восстанавливает логические типы, потерянные в схеме: UUID в SQLite
может оказаться строкой, а enum — обычным VARCHAR. Для сохранения типов используйте
ORM-адаптер. Автообнаружение требует импортированных моделей и не импортирует весь проект.
Поддержка и ограничения редактора связей описаны в разделе [связей](relationships.md).


## Документация Diplodoc

Исходный язык — английский (`docs/en`), перевод — русский (`docs/ru`). Структура страниц и `toc.yaml` совпадает.

Требования: Node.js 24+ и npm 11.5.1+. Из корня репозитория:

```bash
npm ci
npm run docs:build
npm run docs:serve
```

Сборка появляется в `build/docs`. Откройте [localhost:8001](http://localhost:8001/): корневой URL ведёт в английскую версию. Русская версия доступна по `/ru/`. Сборка проверяет состав переводов, ссылки и предупреждения Diplodoc. CI сохраняет HTML как artifact.

Отдельный workflow `pages` публикует готовый каталог `build/docs` из `master` через GitHub Pages Actions.
В Settings → Pages выберите **GitHub Actions** как источник. Не запускайте Jekyll над корнем
репозитория или исходной папкой `docs`: Liquid воспринимает Jinja-примеры `{% extends %}`
как свои теги. Готовый artifact содержит `.nojekyll` и сохраняет ассеты `_bundle` Diplodoc.
Предупреждение Faraday о retry не связано с причиной сбоя сборки.

Новые страницы добавляйте в обе языковые папки и оба `toc.yaml`. Меняйте примеры API синхронно. Настройки находятся в `docs/.yfm`, версия CLI закреплена в `package-lock.json`.
