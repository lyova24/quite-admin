"""Opt-in walkthrough integration for the local examples, not the public Admin API."""

from collections.abc import Callable, Mapping

from quite_admin import Admin

_TOUR_TEMPLATES = frozenset(
    {
        "quite_admin/dashboard.html",
        "quite_admin/list.html",
        "quite_admin/form.html",
        "quite_admin/schema.html",
        "quite_admin/history.html",
    }
)

_STEPS = (
    ("home", "/", "[data-dashboard] .home-search:not([hidden])", None),
    ("list", "/models/products/", ".list-toolbar", None),
    ("form", "/models/products/new", ".record-form .form-field:not(.is-readonly)", None),
    ("relationships", "/models/products/new", "[data-relation-picker]", None),
    (
        "calendar",
        "/models/schedules/new",
        ".form-date-panel:not([hidden])",
        "calendar",
    ),
    ("export", "/models/products/", ".export-form fieldset", "details"),
    ("schema", "/schema", "[data-schema-canvas]", None),
    ("history", "/history", ".history-filters", None),
)

_TEXT = {
    "en": {
        "home": (
            "Find a table",
            "Search the table catalog or open a table from its group. Pinned and recent tables "
            "help you return to your work.",
        ),
        "list": (
            "Search and filter records",
            "Search, filters and column sorting narrow the list. Open a record to review "
            "its fields and related records.",
        ),
        "form": (
            "Record fields",
            "Labels, hints and type-specific controls describe each field. Read-only values "
            "appear separately; changes are saved only when you submit the form.",
        ),
        "relationships": (
            "Choose related records",
            "Search existing records by name or ID. Single relationships accept one choice; "
            "multiple relationships keep your selections across search results and pages.",
        ),
        "calendar": (
            "Dates and time",
            "The shared calendar includes date, time and precision controls. Opening it "
            "does not change the stored record.",
        ),
        "export": (
            "Choose export columns",
            "Select visible fields and fields from related tables. The download includes "
            "all records matching the current search, filters and sorting.",
        ),
        "schema": (
            "Explore the database schema",
            "Explore the tables and their relationships in the diagram. Select a table "
            "to reveal its fields, drag to move around or zoom in for a closer look.",
        ),
        "history": (
            "Review activity",
            "Filter actions by user, table or date. Expand a change to compare the previous "
            "and saved values, or switch between Journal and Table views.",
        ),
    },
    "ru": {
        "home": (
            "Найдите таблицу",
            "Найдите таблицу в каталоге или откройте её группу. Закреплённые и недавние таблицы "
            "помогают вернуться к работе.",
        ),
        "list": (
            "Поиск и фильтры",
            "Поиск, фильтры и сортировка столбцов сужают список. Откройте запись, чтобы "
            "посмотреть её поля и связанные записи.",
        ),
        "form": (
            "Поля записи",
            "Подписи, подсказки и типы контролов поясняют каждое поле. Значения только для "
            "чтения показаны отдельно; изменения сохраняются после отправки формы.",
        ),
        "relationships": (
            "Выбор связанных записей",
            "Ищите существующие записи по имени или ID. Одиночная связь принимает одну запись; "
            "множественная сохраняет выбор между результатами поиска и страницами.",
        ),
        "calendar": (
            "Даты и время",
            "Общий календарь содержит настройки даты, времени и точности. Его открытие "
            "не меняет сохранённую запись.",
        ),
        "export": (
            "Выбор столбцов экспорта",
            "Выберите видимые поля и поля связанных таблиц. В файл попадут все записи "
            "с учётом текущего поиска, фильтров и сортировки.",
        ),
        "schema": (
            "Схема базы данных",
            "Посмотрите таблицы и их связи на диаграмме. Нажмите на таблицу, чтобы раскрыть "
            "её поля, перемещайте схему или увеличивайте масштаб для подробного просмотра.",
        ),
        "history": (
            "История действий",
            "Отфильтруйте действия по пользователю, таблице или дате. Раскройте изменение "
            "для сравнения значений до и после сохранения или переключите журнал и таблицу.",
        ),
    },
}


def build_tour_config(
    url: Callable[[str], str],
    language: str,
    storage_key: str,
    capabilities: Mapping[str, bool] | None = None,
) -> dict:
    """Build metadata-only steps; explicit capabilities omit every unavailable screen."""
    language = "ru" if language == "ru" else "en"
    steps = []
    for name, path, selector, opening in _STEPS:
        if capabilities is not None and not capabilities.get(name, False):
            continue
        title, body = _TEXT[language][name]
        step = {"id": name, "url": url(path), "selector": selector, "title": title, "body": body}
        if opening is not None:
            step["open"] = opening
        steps.append(step)
    return {
        "storageKey": storage_key,
        "language": language,
        "homeUrl": url("/"),
        "steps": steps,
    }


class DemoAdmin(Admin):
    """Keep the example tour opt-in without changing installed Admin defaults or CSP."""

    async def _tour_capabilities(self, request):
        resources = await self.resources()
        products = resources.get("products")
        schedules = resources.get("schedules")
        products_list = products is not None and await self._allowed(request, products, "list")
        products_create = products is not None and await self._allowed(request, products, "create")
        relationships = products_create and any(
            editor["editable"]
            for editor in await self._available_relations(request, products, creating=True)
        )
        calendar = (
            schedules is not None
            and await self._allowed(request, schedules, "create")
            and any(
                field.kind in {"date", "datetime"}
                for field in schedules.options.writable_fields(schedules.schema, True).values()
            )
        )
        schema = False
        for resource in resources.values():
            if await self._allowed(request, resource, "list") and await self._allowed(
                request, resource, "view"
            ):
                schema = True
                break
        return {
            "home": True,
            "list": products_list,
            "form": products_create,
            "relationships": relationships,
            "calendar": calendar,
            "export": products_list and await self._allowed(request, products, "view"),
            "schema": schema,
            "history": await self._history_allowed(request),
        }

    async def _render(self, request, template, *, status=200, trusted_scripts=(), **context):
        context.pop("tour_config", None)
        identity = getattr(request.state, "identity", None)
        if identity is not None and status < 400 and template in _TOUR_TEMPLATES:
            capabilities = await self._tour_capabilities(request)
            context["tour_config"] = build_tour_config(
                lambda path: self._url(request, path),
                self.language,
                f"quite-admin-demo-tour:{self._url(request)}:{identity.subject}",
                capabilities,
            )
            trusted_scripts = (*trusted_scripts, "tour.js")
        return await super()._render(
            request, template, status=status, trusted_scripts=trusted_scripts, **context
        )
