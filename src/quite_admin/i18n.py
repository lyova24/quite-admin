"""Instance-local English and Russian interface messages."""

from __future__ import annotations

from typing import Any, Literal

Language = Literal["en", "ru"]

# Preserve message IDs used by template API 1 while using relational terminology.
MESSAGE_ALIASES = {
    "Collection": "Table",
    "All collections": "All tables",
    "Choose another user or collection, or clear the filters.": (
        "Choose another user or table, or clear the filters."
    ),
    "Other collections": "Other tables",
    (
        "Related collections use one value per line in each cell; missing single "
        "relations are empty. Limits: 10000 records, or 1000 with related columns."
    ): (
        "Related tables use one value per line in each cell; missing single "
        "relations are empty. Limits: 10000 records, or 1000 with related columns."
    ),
    "COLLECTIONS": "TABLES",
    "Collections": "Tables",
    "No collections available.": "No tables available.",
    "Browse your collections and keep things running.": (
        "Browse your tables and keep things running."
    ),
    "Open collection": "Open table",
    "No collections yet": "No tables yet",
    "A new addition to your collection.": "A new addition to your table.",
    "COLLECTION": "TABLE",
    "This collection has no records yet.": "This table has no records yet.",
    "collection": "table",
    "collections": "tables",
}


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
    "Show only related tables": "Показать только связанные таблицы",
    "Restore previous tables": "Вернуть прежний набор таблиц",
    "Remove from recently opened: {name}": "Убрать из недавно открытых: {name}",
    "Home": "Главная",
    "Home view": "Вид главной",
    "Cards": "Карточки",
    "Table list": "Список таблиц",
    "Profile": "Профиль",
    "Expand sidebar": "Развернуть боковую панель",
    "Collapse sidebar": "Свернуть боковую панель",
    "Choose a table to start working.": "Выберите таблицу, чтобы начать работу.",
    "Quick access": "Быстрый доступ",
    "Find a table": "Найти таблицу",
    "Available tables: {count}": "Доступно таблиц: {count}",
    "Groups: {count}": "Групп: {count}",
    "Choose a table from the sidebar.": "Выберите таблицу в боковой панели.",
    "Pinned tables": "Закреплённые таблицы",
    "Manage tables": "Выбрать таблицы",
    "Keep your go-to tables close": "Самые нужные таблицы — рядом",
    "Find a table and pin it with the star. Your shortcuts will appear here.": (
        "Найдите таблицу и закрепите её звёздочкой. Здесь появятся ваши быстрые переходы."
    ),
    "Recently opened": "Недавно открытые",
    "On this browser": "В этом браузере",
    "Tables you open will appear here, so you can pick up where you left off.": (
        "Здесь появятся открытые вами таблицы, чтобы было удобно продолжить работу."
    ),
    "Workspace": "Рабочее пространство",
    "Explore tables, groups and their relationships.": (
        "Изучайте таблицы, группы и связи между ними."
    ),
    "Review actions and changes in your workspace.": (
        "Просматривайте действия и изменения в админке."
    ),
    "Matching tables: {count}": "Найдено таблиц: {count}",
    "Showing first {count} matches. Refine your search.": (
        "Показаны первые {count} совпадений. Уточните поиск."
    ),
    "Pin table: {name}": "Закрепить таблицу: {name}",
    "Unpin table: {name}": "Открепить таблицу: {name}",
    "Pin up to {count} tables.": "Можно закрепить до {count} таблиц.",
    "Search tables (Ctrl/Cmd+K)": "Поиск таблиц (Ctrl/⌘ K)",
    "Use ↑ and ↓ to navigate, Enter to open, Escape to close.": (
        "↑ и ↓ — выбор, Enter — открыть, Escape — закрыть."
    ),
    "Resize sidebar": "Изменить ширину боковой панели",
    "Drag or use arrow keys to resize; double-click to reset.": (
        "Перетащите или используйте стрелки для изменения ширины; двойной щелчок сбрасывает её."
    ),
    "Show full value": "Показать полностью",
    "Copy value": "Скопировать значение",
    "Copy": "Копировать",
    "Value copied": "Значение скопировано",
    "Copy the selected value with Ctrl+C or ⌘C.": "Скопируйте выделенное значение: Ctrl+C или ⌘C.",
    "Delete selected records": "Удалить выбранные записи",
    "Selected record": "Выбранная запись",
    "Select record": "Выбрать запись",
    "Select all records on this page": "Выбрать все записи на странице",
    "Selected records: {count}": "Выбрано записей: {count}",
    "Succeeded: {count}": "Успешно: {count}",
    "Failed: {count}": "С ошибкой: {count}",
    "Bulk actions": "Массовые действия",
    "Bulk action results": "Результат массового действия",
    "Confirm bulk action": "Подтвердите массовое действие",
    "With selected": "С выбранными",
    "Continue": "Продолжить",
    "Confirm action": "Подтвердить действие",
    "Back to records": "Вернуться к записям",
    (
        "Each record is processed separately. "
        "Successful changes remain saved if another record fails."
    ): (
        "Каждая запись обрабатывается отдельно. Успешные изменения сохраняются, "
        "даже если другая запись вызвала ошибку."
    ),
    "Invalid bulk selection.": "Некорректный выбор записей.",
    "Select between 1 and 100 records.": "Выберите от 1 до 100 записей.",
    "Select between 1 and 100 distinct records.": "Выберите от 1 до 100 разных записей.",
    "The bulk confirmation expired or is invalid. Select records again.": (
        "Подтверждение массового действия истекло или некорректно. Выберите записи заново."
    ),
    "The record changed. Select it again before performing this action.": (
        "Запись изменилась. Выберите её заново перед выполнением действия."
    ),
    "Unable to complete this action.": "Не удалось выполнить действие.",
    "Activity journal": "Журнал изменений",
    "Activity view": "Вид истории",
    "Journal": "Журнал",
    "Table": "Таблица",
    "Who changed what, with field values before and after.": (
        "Кто и что изменил: значения полей до и после сохранения."
    ),
    "Changes only": "Только изменения",
    "Today": "Сегодня",
    "Yesterday": "Вчера",
    "Field": "Поле",
    "Before": "Было",
    "After": "Стало",
    "Field changes": "Изменения полей",
    "Changed fields: {count}": "Изменено полей: {count}",
    "Expand all changes": "Развернуть все изменения",
    "Collapse all changes": "Свернуть все изменения",
    "Not present": "Отсутствует",
    "Empty string": "Пустая строка",
    "Value truncated": "Значение сокращено",
    "Additional changes omitted: {count}": "Дополнительных изменений не показано: {count}",
    "Changes were not saved.": "Изменения не сохранены.",
    "Field details were not recorded for this event.": (
        "Для этого события значения полей не сохранялись."
    ),
    "No visible field changes.": "Нет изменений доступных полей.",
    "Show all activity": "Показать все действия",
    "Activity history": "История действий",
    "User": "Пользователь",
    "Collection": "Таблица",
    "Create": "Создание",
    "Export": "Экспорт",
    "Apply": "Применить",
    "All users": "Все пользователи",
    "All collections": "Все таблицы",
    "Authentication": "Авторизация",
    "Action": "Действие",
    "All actions": "Все действия",
    "Custom action": "Пользовательское действие",
    "Result": "Результат",
    "All results": "Все результаты",
    "Success": "Успешно",
    "Failure": "Ошибка",
    "Time (UTC)": "Время (UTC)",
    "Date from (UTC)": "Дата с (UTC)",
    "Date to (UTC)": "Дата по (UTC)",
    "Period (UTC)": "Период (UTC)",
    "Any date": "Любая дата",
    "Specific day": "Конкретный день",
    "Date range": "От–до",
    "Date (UTC)": "Дата (UTC)",
    "Choose period": "Выбрать период",
    "Search by name or identifier.": "Поиск по имени или идентификатору.",
    "Month": "Месяц",
    "Quick select": "Быстрый выбор",
    "Commonly used": "Часто используемые",
    "Last 7 days": "Последние 7 дней",
    "Last 30 days": "Последние 30 дней",
    "This month": "Этот месяц",
    "Apply period": "Применить период",
    "Full days, inclusive · UTC": "Полные дни, включительно · UTC",
    "From {date}": "С {date}",
    "To {date}": "По {date}",
    "Invalid history date range.": "Некорректный период истории.",
    "Inline update": "Изменение в списке",
    "Update": "Изменение",
    "No activity found": "Действия не найдены",
    "Choose another user or collection, or clear the filters.": (
        "Выберите другого пользователя или таблицу либо сбросьте фильтры."
    ),
    "Latest events": "Последние события",
    "Older events": "Более ранние события",
    "Invalid history filters.": "Некорректные фильтры истории.",
    "Invalid history cursor.": "Некорректный курсор истории.",
    "The admin storage is unavailable.": "Служебное хранилище админки недоступно.",
    "{count} on this page": "{count} на этой странице",
    "Browse records": "Просмотр записей",
    "The database query timed out. Narrow the filters and try again.": (
        "Превышено время запроса к БД. Уточните фильтры и повторите попытку."
    ),
    "Enter a value of at least {minimum}.": "Введите значение не меньше {minimum}.",
    "Enter a value of at most {maximum}.": "Введите значение не больше {maximum}.",
    "The database rejected these values.": "База данных отклонила эти значения.",
    "Close": "Закрыть",
    "Does not equal": "Не равно",
    "Contains": "Содержит",
    "Does not contain": "Не содержит",
    "Starts with": "Начинается с",
    "Ends with": "Заканчивается на",
    "Is one of": "Одно из значений",
    "On date": "За дату",
    "Is empty text": "Пустая строка",
    "Is not empty text": "Непустая строка",
    "Add another condition": "Добавить ещё условие",
    "Search values": "Поиск значений",
    "One value per line": "По одному значению на строку",
    "Match any selected value; other conditions must also match.": (
        "Подходит любое выбранное значение; остальные условия также должны выполняться."
    ),
    "Date": "Дата",
    (
        "Includes the whole day. Leave the offset empty for database-local "
        "time, or enter Z / ±HH:MM."
    ): ("Включает весь день. Пустое смещение — время БД; либо укажите Z / ±HH:MM."),
    "For example, Alex": "Например, Alex",
    "Partial text ignores case. %, _ and ! are literal characters; NULL is separate.": (
        "Поиск по части текста без учёта регистра. %, _ и ! — обычные "
        "символы; NULL задаётся отдельно."
    ),
    "Enter valid values.": "Введите корректные значения.",
    "Choose between 1 and 100 values.": "Выберите от 1 до 100 значений.",
    "Search text or an exact ID. Searchable fields:": (
        "Поиск по тексту или точному ID. Текстовые поля:"
    ),
    "Searchable fields:": "Поля поиска:",
    "Text": "Текст",
    "Integer": "Целое число",
    "Number": "Число",
    "Boolean": "Логическое значение",
    "Choice": "Выбор",
    "Date and time": "Дата и время",
    "Time": "Время",
    "Precision and timezone": "Точность и часовой пояс",
    "More options": "Дополнительно",
    "Choose a date.": "Выберите дату.",
    "Enter a time.": "Введите время.",
    "Related record": "Связанная запись",
    "Binary": "Двоичные данные",
    "Other": "Другое",
    "Enter a JSON list of text values.": "Введите JSON-массив текстовых значений.",
    "Choose a date, with an optional UTC offset.": (
        "Выберите дату и при необходимости смещение UTC."
    ),
    "This adapter does not support this condition.": "Адаптер не поддерживает это условие.",
    "The record changed. Reload the list before switching again.": (
        "Запись изменилась. Обновите список перед повторным переключением."
    ),
    "Edit field": "Изменить поле",
    "Unable to save. Review permissions or reload the list.": (
        "Не удалось сохранить. Проверьте права или обновите список."
    ),
    "Choose date": "Выбрать дату",
    "Choose date and time": "Выбрать дату и время",
    "Choose time": "Выбрать время",
    "Choose date range": "Выбрать диапазон дат",
    "Choose time range": "Выбрать диапазон времени",
    "Invalid date/time value.": "Некорректная дата или время.",
    "The lower bound must not exceed the upper bound.": (
        "Начало диапазона не может быть позже конца."
    ),
    "Previous month": "Предыдущий месяц",
    "Next month": "Следующий месяц",
    "Year": "Год",
    "Other collections": "Другие таблицы",
    "Format JSON": "Форматировать JSON",
    "Valid JSON": "Корректный JSON",
    "Invalid JSON": "Ошибка синтаксиса JSON",
    "JSON is too large for highlighting.": "JSON слишком большой для подсветки.",
    "JSON nesting is too deep to format.": "Слишком глубокая вложенность JSON для форматирования.",
    "Fractional seconds (optional)": "Доли секунды (необязательно)",
    "UTC offset (optional)": "Смещение UTC (необязательно)",
    "Use Z or ±HH:MM; leave empty for no timezone.": (
        "Укажите Z или ±HH:MM; оставьте пустым для времени без часового пояса."
    ),
    "Export data": "Экспорт данных",
    "Columns": "Столбцы",
    "Format": "Формат",
    "Download": "Скачать",
    (
        "Exports all matching records using the current search, filters and sorting. "
        "Apply filters before exporting."
    ): (
        "Выгружаются все подходящие записи с текущим поиском, фильтрами и "
        "сортировкой. Сначала примените фильтры."
    ),
    (
        "Related collections use one value per line in each cell; missing single "
        "relations are empty. Limits: 10000 records, or 1000 with related columns."
    ): (
        "Связи ко многим выгружаются построчно внутри ячеек; отсутствующие одиночные "
        "связи пустые. Лимит: 10000 записей или 1000 со связанными столбцами."
    ),
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
    "Expand view": "Развернуть схему",
    "Exit expanded view": "Обычный вид",
    "Database schema": "Схема БД",
    "Interactive database schema": "Интерактивная схема базы данных",
    "Tables and relationships": "Таблицы и связи",
    "Tables": "Таблицы",
    "Show table": "Показать таблицу",
    "Show group": "Показать группу",
    (
        "Group checkboxes select every table in the group, including tables hidden by search."
    ): "Флажки групп выбирают все таблицы группы, включая скрытые поиском.",
    "Visible tables": "Отображаемые таблицы",
    "Search tables": "Поиск таблиц",
    "Show all": "Показать все",
    "Hide all": "Скрыть все",
    "Select tables to display": "Выберите таблицы для показа",
    (
        "There are too many tables to display automatically. "
        "Select tables in the sidebar, or choose Show all."
    ): (
        "Таблиц слишком много для автоматического отображения. "
        "Выберите таблицы в боковой панели или нажмите «Показать все»."
    ),
    "No matching tables.": "Таблицы не найдены.",
    "Find table": "Найти таблицу",
    "Zoom in": "Приблизить",
    "Zoom out": "Отдалить",
    "Fit schema": "Вся схема",
    "Auto layout": "Автокомпоновка",
    "Show all fields": "Все поля",
    "Show key fields": "Ключевые поля",
    "Show junction table": "Показать промежуточную таблицу",
    "Hide junction table": "Скрыть промежуточную таблицу",
    "Junction tables": "Промежуточные таблицы",
    "No visible fields": "Нет доступных полей",
    "One to one": "Один к одному",
    "One to many": "Один ко многим",
    "Many to many": "Многие ко многим",
    "Foreign key": "Внешний ключ",
    "Enable JavaScript to use the interactive schema.": (
        "Включите JavaScript для интерактивной схемы."
    ),
    (
        "Click a table to expand fields; click M:N to reveal its junction. "
        "Drag to move. Ctrl/⌘ + scroll to zoom."
    ): (
        "Нажмите таблицу для раскрытия полей, M:N — для промежуточной таблицы. "
        "Перетаскивайте для перемещения. Ctrl/⌘ + прокрутка меняет масштаб."
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
    "Overview": "Обзор",
    "COLLECTIONS": "ТАБЛИЦЫ",
    "Collections": "Таблицы",
    "No collections available.": "Нет доступных таблиц.",
    "PAGES": "СТРАНИЦЫ",
    "Custom pages": "Свои страницы",
    "Show sidebar": "Показать боковую панель",
    "Hide sidebar": "Скрыть боковую панель",
    "Sign out": "Выйти",
    "YOUR WORKSPACE, AT A GLANCE": "ВАШЕ РАБОЧЕЕ ПРОСТРАНСТВО",
    "Browse your collections and keep things running.": (
        "Просматривайте таблицы и управляйте записями."
    ),
    "Ready to explore": "Готовы к работе",
    "Open collection": "Открыть таблицу",
    "No collections yet": "Таблиц пока нет",
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
    "A new addition to your collection.": "Новая запись в вашей таблице.",
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
    "COLLECTION": "ТАБЛИЦА",
    "A little order for every record.": "Все записи таблицы в одном месте.",
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
    "This collection has no records yet.": "В этой таблице пока нет записей.",
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
    "Table not found.": "Таблица не найдена.",
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
    "table": ("таблица", "таблицы", "таблиц"),
    "relationship": ("связь", "связи", "связей"),
    "record": ("запись", "записи", "записей"),
    "collection": ("таблица", "таблицы", "таблиц"),
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


# Keep direct dictionary consumers and the browser demo compatible with old IDs.
RUSSIAN.update(
    {
        canonical: RUSSIAN[legacy]
        for legacy, canonical in MESSAGE_ALIASES.items()
        if legacy in RUSSIAN
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
        message = MESSAGE_ALIASES.get(message, message)
        translated = RUSSIAN.get(message, message) if self.language == "ru" else message
        return translated.format(**values) if values else translated

    def ngettext(self, singular: str, plural: str, count: int) -> str:
        singular = MESSAGE_ALIASES.get(singular, singular)
        plural = MESSAGE_ALIASES.get(plural, plural)
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
