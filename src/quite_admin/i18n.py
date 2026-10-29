"""Instance-local English and Russian interface messages."""

from __future__ import annotations

from typing import Any, Literal

Language = Literal["en", "ru"]


class Message(str):
    """Keep validation parameters while preserving the public English string API."""

    template: str
    values: dict[str, Any]

    def __new__(cls, template: str, **values: Any) -> Message:
        instance = super().__new__(cls, template.format(**values))
        instance.template = template
        instance.values = values
        return instance


RUSSIAN = {
    "Add filter": "Добавить фильтр",
    "Find a field…": "Найти поле…",
    "Back": "Назад",
    "Condition": "Условие",
    "Value": "Значение",
    "Greater than": "Больше",
    "At least": "Не меньше",
    "Less than": "Меньше",
    "At most": "Не больше",
    "Between": "Между",
    "Apply filter": "Применить",
    "No matching fields.": "Подходящих полей нет.",
    "This condition already exists. Edit the existing filter.": (
        "Такое условие уже есть. Измените существующий фильтр."
    ),
    "All conditions must match.": "Все условия должны выполняться.",
    "Use an ISO date or time, including a timezone if needed.": (
        "Дата или время в формате ISO; при необходимости укажите часовой пояс."
    ),
    "Filters": "Фильтры",
    "Active filters": "Активные фильтры",
    "Apply filters": "Применить фильтры",
    "Clear all": "Сбросить всё",
    "Any value": "Любое значение",
    "Equals": "Равно",
    "From": "От",
    "To": "До",
    "Empty values": "Пустые значения",
    "Any empty value state": "С NULL и без NULL",
    "Is NULL": "Равно NULL",
    "Is not NULL": "Не равно NULL",
    "Invalid filter.": "Некорректный фильтр.",
    "Please correct the highlighted filters.": "Исправьте выделенные фильтры.",
    "Filter value is too long.": "Слишком длинное значение фильтра.",
    "The upper bound must be greater than or equal to the lower bound.": (
        "Верхняя граница должна быть не меньше нижней."
    ),
    "Use compatible date and time values.": "Используйте совместимые значения даты и времени.",
    "At most 50 filters are supported.": "Допускается не более 50 фильтров.",
    "At most 10 relationship filters are supported.": "Допускается не более 10 фильтров по связям.",
    "Try different filters or search.": "Измените фильтры или поисковый запрос.",
    "Choose records": "Выбрать записи",
    "Search related records": "Поиск связанных записей",
    "Remove": "Убрать",
    "Loading…": "Загрузка…",
    "No matching records.": "Совпадений нет.",
    "Could not load records. Try again.": "Не удалось загрузить записи. Попробуйте ещё раз.",
    "Retry": "Повторить",
    "Selected": "Выбрано",
    "Results": "Найдено",
    "Select up to 1000 records.": "Можно выбрать до 1000 записей.",
    "Unavailable record": "Запись недоступна",
    "Enable JavaScript to search all related records.": (
        "Включите JavaScript для поиска всех связанных записей."
    ),
    "More than 1000 linked records. Editing is disabled to preserve the complete selection.": (
        "Связано более 1000 записей. Редактирование отключено, чтобы сохранить полный состав связи."
    ),
    "WORKSPACE": "РАБОЧЕЕ ПРОСТРАНСТВО",
    "Workspace": "Рабочее пространство",
    "Overview": "Обзор",
    "COLLECTIONS": "КОЛЛЕКЦИИ",
    "Collections": "Коллекции",
    "No collections available.": "Нет доступных коллекций.",
    "PAGES": "СТРАНИЦЫ",
    "Custom pages": "Свои страницы",
    "Sign out": "Выйти",
    "YOUR WORKSPACE, AT A GLANCE": "ВАШЕ РАБОЧЕЕ ПРОСТРАНСТВО",
    "Browse your collections and keep things running.": (
        "Просматривайте коллекции и управляйте записями."
    ),
    "Ready to explore": "Готовы к работе",
    "Open collection": "Открыть коллекцию",
    "No collections yet": "Коллекций пока нет",
    "Connect an adapter or register an existing model in your application.": (
        "Подключите адаптер или зарегистрируйте существующую модель в приложении."
    ),
    "Your pages": "Ваши страницы",
    "Delete this record?": "Удалить эту запись?",
    "This will permanently remove the record. Database cascade rules also apply.": (
        "Запись будет удалена без возможности восстановления. "
        "Также применяются каскадные правила базы данных."
    ),
    "Keep record": "Оставить запись",
    "Delete permanently": "Удалить навсегда",
    "Reload record": "Перечитать запись",
    (
        "This record changed after you opened it. Your changes have not been saved. "
        "Reload the record and review the latest values."
    ): (
        "Запись изменилась после открытия. Ваши изменения не сохранены. "
        "Перечитайте запись и проверьте актуальные значения."
    ),
    "Record fields": "Поля записи",
    "Structured data": "Структурированные данные",
    "Read-only fields": "Неизменяемые поля",
    "Relationships": "Связи",
    "Record details": "Просмотр записи",
    "Delete record": "Удалить запись",
    "Edit record": "Редактировать запись",
    "Primary key": "Первичный ключ",
    "None": "Нет значения",
    "Something needs your attention.": "Требуется ваше внимание.",
    "Back to workspace": "Вернуться к обзору",
    "Create record": "Создать запись",
    "A new addition to your collection.": "Новая запись в вашей коллекции.",
    "Make a change. Keep everything in order.": "Измените значения полей и сохраните запись.",
    "Please correct the highlighted fields.": "Исправьте выделенные поля.",
    "Read only": "Только чтение",
    "optional": "необязательно",
    "True": "Да",
    "False": "Нет",
    "Use model / database default": "Использовать значение по умолчанию модели / базы данных",
    "References {target}. Enter the related key.": (
        "Ссылка на {target}. Введите ключ связанной записи."
    ),
    "Generated values are filled automatically.": (
        "Генерируемые значения заполняются автоматически."
    ),
    "Primary keys and generated fields are read only.": (
        "Первичные ключи и генерируемые поля доступны только для чтения."
    ),
    "Cancel": "Отмена",
    "Save changes": "Сохранить изменения",
    "COLLECTION": "КОЛЛЕКЦИЯ",
    "A little order for every record.": "Все записи коллекции в одном месте.",
    "Search records": "Поиск записей",
    "Search records…": "Поиск записей…",
    "Search": "Найти",
    "Clear": "Сбросить",
    "Actions": "Действия",
    "View": "Просмотр",
    "Edit": "Изменить",
    "Delete": "Удалить",
    "No matching records": "Совпадений не найдено",
    "A fresh start.": "Здесь пока пусто.",
    "Try a different search.": "Попробуйте другой поисковый запрос.",
    "This collection has no records yet.": "В этой коллекции пока нет записей.",
    "Create your first record": "Создать первую запись",
    "Page {number}": "Страница {number}",
    "{count} per page": "По {count} на странице",
    "Previous": "Назад",
    "Next": "Далее",
    "Sign in": "Войти",
    "Sign in to your workspace to continue.": "Войдите в рабочее пространство, чтобы продолжить.",
    "Username": "Имя пользователя",
    "Password": "Пароль",
    "Your data. A little more organized.": "Ваши данные. Всё на своих местах.",
    "Too many attempts. Try again shortly.": "Слишком много попыток. Попробуйте немного позже.",
    "Invalid username or password.": "Неверное имя пользователя или пароль.",
    "Credentials are too long.": "Имя пользователя или пароль слишком длинные.",
    "Table not found.": "Коллекция не найдена.",
    "Record not found.": "Запись не найдена.",
    "Page not found.": "Страница не найдена.",
    "You do not have permission to perform this action.": "У вас нет прав на это действие.",
    "You do not have permission to view this page.": "У вас нет прав на просмотр этой страницы.",
    "Expected a URL-encoded form.": "Ожидается форма в формате URL-encoded.",
    "The form exceeds 1 MiB.": "Размер формы превышает 1 МиБ.",
    "Duplicate form fields are not accepted.": "Повторяющиеся поля формы не допускаются.",
    "Invalid CSRF token. Reload the form and try again.": (
        "Недействительный CSRF-токен. Обновите форму и попробуйте снова."
    ),
    "Invalid pagination.": "Некорректные параметры страниц.",
    "Invalid sort field.": "Некорректное поле сортировки.",
    "The operation conflicts with a database constraint.": (
        "Операция нарушает ограничение базы данных."
    ),
    "This field has no writable default.": "У этого поля нет доступного значения по умолчанию.",
    "This field is not writable.": "Это поле недоступно для записи.",
    "A value is required.": "Укажите значение.",
    "Choose true or false.": "Выберите «Да» или «Нет».",
    "Expected a JSON {type}.": "Ожидается JSON типа {type}.",
    "Enter a finite number.": "Введите конечное число.",
    "Use at most {count} characters.": "Используйте не более {count} символов.",
    "Choose one of the available values.": "Выберите одно из доступных значений.",
    "Enter a valid {kind}.": "Введите корректное значение (тип: {kind}).",
    "Not Found": "Страница не найдена",
    "Method Not Allowed": "Метод не разрешён",
    "Bad Request": "Некорректный запрос",
    "Request Entity Too Large": "Слишком большой запрос",
}

RUSSIAN_PLURALS = {
    "record": ("запись", "записи", "записей"),
    "collection": ("коллекция", "коллекции", "коллекций"),
    "field": ("поле", "поля", "полей"),
}

RUSSIAN.update(
    {
        "Open": "Открыть",
        "Back": "Назад",
        "Breadcrumbs": "Навигационная цепочка",
        "No records": "Нет записей",
        "Record": "Запись",
        "Open record": "Открыть запись",
        "Unknown relationship.": "Связь не найдена.",
        "This relationship is read only.": "Эта связь доступна только для чтения.",
        "This relationship is not writable.": "Эта связь недоступна для записи.",
        "Choose a single related record.": "Выберите одну связанную запись.",
        "Related record not found.": "Связанная запись не найдена.",
        "This relationship cannot be detached.": "Эту связь нельзя удалить.",
        "A related record is required.": "Выберите связанную запись.",
        "Invalid relationship selection.": "Некорректный выбор связанных записей.",
        "Hold Ctrl or Command to select multiple records.": (
            "Удерживайте Ctrl или Command для выбора нескольких записей."
        ),
        "The relationship picker is limited to 1000 records. Existing selections are preserved.": (
            "В списке доступно до 1000 записей. Текущий выбор сохраняется."
        ),
    }
)


class Translator:
    def __init__(self, language: Language) -> None:
        if language not in ("en", "ru"):
            raise ValueError("language must be 'en' or 'ru'.")
        self.language = language

    def gettext(self, message: str, **values: Any) -> str:
        if isinstance(message, Message):
            values = {**message.values, **values}
            message = message.template
        translated = RUSSIAN.get(message, message) if self.language == "ru" else message
        return translated.format(**values) if values else translated

    def ngettext(self, singular: str, plural: str, count: int) -> str:
        if self.language == "ru" and singular in RUSSIAN_PLURALS:
            count = abs(count)
            if 11 <= count % 100 <= 14:
                index = 2
            elif count % 10 == 1:
                index = 0
            elif 2 <= count % 10 <= 4:
                index = 1
            else:
                index = 2
            return RUSSIAN_PLURALS[singular][index]
        return self.gettext(singular if count == 1 else plural)
