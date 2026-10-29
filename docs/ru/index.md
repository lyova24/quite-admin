# quite-admin

Встраиваемая админка для **FastAPI** и **Litestar**, Python 3.11–3.15.
Таблицы, поля и формы собираются из существующей схемы. Дополнительные Pydantic-модели,
DTO и классы `ModelAdmin` не нужны. MIT License.

| Режим | Источник схемы | Когда использовать |
| --- | --- | --- |
| **SQL reflection** | Таблицы и колонки самой БД | Любая ORM поверх SQL или приложение без ORM; модели импортировать не нужно |
| **ORM adapter** | Существующие классы ORM | Нужны Python defaults, типы моделей и их persistence hooks |

Встроены адаптеры SQLAlchemy 2.x / SQLModel, Tortoise ORM и Peewee. Контракт
`Adapter` позволяет подключать другие ORM, документные БД и собственные repositories.
«Любая ORM» означает независимое ядро и SQL reflection для SQL-баз, а не
автоматическое угадывание произвольного Python API.


[English](../en/index.md) · [Быстрый старт](quickstart.md)

![Список записей](../assets/screenshots/products.png)

[12-секундный обзор интерфейса](../assets/walkthrough.mp4)

## Возможности

- Просмотр, создание, редактирование и удаление записей.
- Поиск, сортировка и пагинация.
- Скрытые и read-only поля, права на операции.
- Авторизация, CSRF и серверная проверка полей.
- Свои страницы и Jinja2-шаблоны.
- Интерфейс на английском и русском, свои цвета, название и описание админки.

Начните с [подключения](integration.md) или [демо](quickstart.md).
Настройте [язык и оформление](customization.md) для своего приложения.

## Выбор интеграции

| Проект | Подходящий сценарий |
|---|---|
| quite-admin | Автообнаружение SQL-схемы, FastAPI/Litestar, Peewee, несколько ORM или сервисный адаптер; ранняя разработка с явно указанными ограничениями |
| [SQLAdmin](https://github.com/smithyhq/sqladmin) | SQLAlchemy/SQLModel views, sync/async engine и WTForms с FastAPI/Starlette |
| [Starlette Admin](https://github.com/jowilf/starlette-admin) | Contrib model views, MongoDB, bulk actions, файлы и import/export |

Выбор основан на документированных способах подключения. Перед использованием
проверьте [матрицу ORM/СУБД](data-safety.md), включая ещё не подтверждённые сочетания.
