# Регистрация и поля

По умолчанию скрываются имена с `password`, имена `secret`, `token`, `credentials`,
`authorization`, `api_key`, `private_key`, `session_key`, а также окончания `_token`
и `_secret`. `exclude` всегда имеет приоритет. Эвристика не находит все секреты —
проверяйте обнаруженную схему. Для явного исключения есть
`expose_sensitive_fields=("api_key",)`.

Поля `created_at`, `updated_at`, `deleted_at`, `created_by`, `updated_by`, `is_admin`,
`is_superuser`, `is_staff`, `roles`, `permissions` по умолчанию только для чтения.
Явно разрешить изменение можно через `writable_protected_fields=("is_admin",)`.
Это не отменяет ограничения `readonly_fields`, generated и read-only метаданные адаптера.
Defaults отличаются от 0.1.0: при обновлении укажите необходимые исключения явно.
Скрытие PK не делает идентификатор секретным: ключ закодирован в URL записи.

## Собственные контролы полей

`FieldOptions` принимает `kind`, `parser`, `formatter`, `template`. Пример счётчика `#7`:

```python
FieldOptions(
    kind="string",
    parser=lambda raw: int(raw.removeprefix("#")),
    formatter=lambda value: "#" + str(value),
    template="counter.html",
)
```

Parser возвращает нативное значение или выбрасывает `ValueError`. Formatter возвращает
текст, который экранируется шаблонами. Шаблон получает `field`, `values`, `errors`
и общий контекст. Контрол должен иметь имя `{{ field.name }}` и значение
`values[field.name]`. Шаблон включается только для writable-поля; серверный allowlist,
подпись и отображение ошибок сохраняются. Неизвестные типы адаптера остаются read-only,
пока собственный адаптер явно не опишет поддерживаемый тип/codec. См. [расширения](extensions.md).

У существующей записи одна страница просмотра и редактирования. Без права изменения поля
доступны только для чтения, а прямой POST отклоняется сервером. `edit_fields` определяет порядок
и набор редактируемых полей; остальные видимые поля показываются там же только для чтения.
Старый GET-адрес `/edit` перенаправляет на страницу записи; POST сохранён как совместимый псевдоним.
Нажатие на строку таблицы открывает запись. Ссылка поддерживает клавиатуру и открытие в новой вкладке.
Отдельно в строке остаётся только удаление, ведущее на подтверждение.
Без права просмотра/изменения ссылки на запись нет; кнопка удаления зависит от права удаления.

Автообнаружение можно отключить и зарегистрировать только нужные модели:

```python
from quite_admin import FieldOptions, ModelOptions

admin = Admin(auth=auth_backend, secret_key=session_secret)
admin.add_adapter(adapter, discover=False)
admin.register(User, options=ModelOptions(
    label="Пользователи",
    list_fields=("id", "email", "is_active"),
    edit_fields=("email", "is_active", "created_at"),
    create_fields=("email", "is_active"),
    readonly_fields=("created_at",),
    exclude=("password_hash",),
    search_fields=("email",),
    fields={"email": FieldOptions(label="Email", help_text="Адрес для уведомлений")},
    can_create=False,
    can_delete=False,
))
```

Тот же `ModelOptions` работает для всех адаптеров. Если автообнаружение включено,
`register()` переопределяет настройки модели. Для reflection используйте
`admin.configure("table_name", options=...)` без импорта модели.

- `list_fields` задаёт колонки списка; по умолчанию показываются первые шесть.
- `edit_fields` / `create_fields` задают порядок и набор полей форм.
- `readonly_fields` и `FieldOptions(read_only=True)` оставляют значение видимым, запрещая запись.
- `exclude` полностью скрывает поле и запрещает его запись и поиск по нему.
- Primary key нельзя менять после создания. Generated, computed, binary и неизвестные
  типы нельзя редактировать. Неавтоматический primary key можно задать при создании.
- Неизвестные, скрытые и read-only поля в POST отклоняются сервером с `422`.
  Опечатка в конфигурации полей вызывает ошибку конфигурации.
- Для default форма предлагает **Use model / database default**. Снимите отметку,
  чтобы задать значение. Пустое nullable-поле означает `NULL`; пустая non-null строка — `""`.

Поддержаны строки, целые, bool, float, Decimal, UUID, ISO date/time/datetime,
JSON и enum. Foreign keys отображаются как скалярные поля с подсказкой о целевой таблице.
Если скрытое или read-only обязательное поле не имеет default, отключите создание
записей либо используйте адаптер, заполняющий его через application service.

Несколько ORM в одном приложении:

```python
admin.add_adapter(sqlalchemy_adapter, namespace="billing")
admin.add_adapter(tortoise_adapter, namespace="catalog")
# /admin/models/billing-orders/ и /admin/models/catalog-products/
```

При нескольких адаптерах `register(..., adapter=adapter)` выбирает источник явно.
Конфликтующие имена требуют `namespace` или `ModelOptions(slug=...)`.
