# Контролы полей и собственные виджеты

Контрол выбирается по метаданным адаптера: строки с ограничением используют input,
TEXT — textarea, даты и время — общий календарь, JSON — локальный редактор,
boolean — переключатель с учётом NULL, enum — select. Полная
[таблица контролов](configuration.md) описывает точность и работу без JavaScript.

## Выбор способа настройки

| Задача | Настройка |
|---|---|
| Изменить подпись, подсказку или read-only | `FieldOptions(label=..., help_text=..., read_only=True)` |
| Разобрать или отформатировать прикладное значение | `FieldOptions(parser=..., formatter=...)` |
| Отрисовать свой input | `FieldOptions(template="counter.html")` и `Admin(templates_dir="templates")` |
| Запросить пароль или значение, отсутствующее в модели | `ModelOptions(input_fields=(Field(...),))` и [handler записи](extensions.md) |
| Проверить форму через Pydantic 2 | `create_schema` / `update_schema` и extra `pydantic` |
| Изменить компоновку и цвета | [Theme, CSS с того же origin и шаблоны](styling.md) |

Реестр именованных виджетов и автоматическая регистрация своего JavaScript отсутствуют.
Используйте описанные расширения; пользовательские шаблоны соблюдают существующий CSP.

## Отрисовка и разбор своего input

Для целого числа в виде `#7` настройте поле коллекции:

```python
from quite_admin import FieldOptions, ModelOptions

admin.configure("products", options=ModelOptions(fields={
    "stock": FieldOptions(
        label="Stock", help_text="Use # followed by a whole number",
        parser=lambda raw: int(raw.removeprefix("#")),
        formatter=lambda value: "#" + str(value),
        template="counter.html",
    ),
}))
```

Создайте `templates/counter.html` в настроенном `templates_dir`:

```jinja
{% set described_by %}{% if help and help.help_text %}help-{{ field.name }} {% endif %}{% if errors.get(field.name) %}error-{{ field.name }}{% endif %}{% endset %}
<input id="field-{{ field.name }}" name="{{ field.name }}" type="text"
       value="{{ values.get(field.name, '') }}"
       aria-invalid="{{ 'true' if errors.get(field.name) else 'false' }}"
       {% if described_by|trim %}aria-describedby="{{ described_by|trim }}"{% endif %}>
```

Внешняя форма добавляет подпись, подсказку, ошибку, CSRF и ревизию. Include получает
`field`, `help`, `values`, `errors`, `editable` и общий контекст шаблона. Сохраняйте
autoescape, отправляйте одно каноническое значение под `field.name` и поддерживайте
управление с клавиатуры. Parser возвращает нативное значение или выбрасывает
`ValueError`: сообщение становится ошибкой поля. Formatter возвращает экранируемый текст.

Свой шаблон используется только для изменяемых полей формы. Такие поля редактируются
на полной странице записи, без inline-правок. Шаблон и parser не предоставляют прав
на скрытые/read-only поля и не отменяют ограничения адаптера.

## Пароли и поля только для форм

Объявите `Field("password", kind="password")` в `input_fields` и handler, который проверяет
и хеширует пароль, сохраняя реальные колонки модели. Контрол пароля остаётся пустым
после ошибок и имеет приоритет над своим шаблоном. Поля только для форм исключены
из списков, поиска, экспорта, ревизий и деталей истории.
Полный контракт описан в разделе [полей только для форм](configuration.md).

Схема Pydantic проверяет форму после прав, CSRF и скалярного разбора, до hooks и записи.
Она не создаёт дополнительные контролы. Для частичных/inline-изменений используйте
необязательные поля update-схемы; см. [сервисы и схемы форм](extensions.md).
