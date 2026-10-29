# Кастомизация оформления

Используйте `Theme` для палитры, CSS-токены для пропорций и плотности, переопределение
шаблонов для структуры. Настройки относятся к экземпляру `Admin` и работают со всеми
адаптерами. Сборка frontend не требуется.

## Палитра и название

```python
from quite_admin import Admin, Theme

admin = Admin(
    auth=auth_backend,
    secret_key=session_secret,
    title="Operations",
    logo="assets/company.svg",
    theme=Theme(
        primary="#345c50",
        background="#f5f6f8",
        surface="#ffffff",
        text="#20252b",
        muted="#626b76",
        border="#dce0e5",
        danger="#b43e3e",
    ),
    templates_dir="templates",
)
```

Акцент выделяет основные действия и выбранные элементы. `danger` обозначает удаление
и ошибки. Boolean остаётся нейтральным; смена палитры не меняет значения статусов.
`on_primary` и `on_danger` задают текст кнопок. Полный набор значений по умолчанию
и пример тёмной темы находятся в [справочнике палитры](customization.md).

## Подключение своего CSS

Раздавайте CSS с **того же origin**, что и админку. Пример для FastAPI:

```python
from starlette.staticfiles import StaticFiles

# app — существующее FastAPI-приложение в корне origin.
app.mount("/admin-style", StaticFiles(directory="admin-style"), name="admin-style")
admin.mount_fastapi(app)
```

В Litestar подключите статический router приложения с тем же публичным путём.
Создайте `admin-style/custom.css`. Для подключения на всех экранах один раз скопируйте
базовый шаблон в каталог переопределений:

```python
from importlib.resources import files
from pathlib import Path

output = Path("templates/quite_admin/base.html")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    files("quite_admin").joinpath("templates/quite_admin/base.html").read_text(),
    encoding="utf-8",
)
```

В копии замените пустой блок `head`:

```jinja
{% block head %}
<link rel="stylesheet" href="/admin-style/custom.css">
{% endblock %}
```

CSS загружается **после** базовых стилей и `theme.css`. Укажите в `href` публичный URL
ассета приложения с учётом deployment/proxy-префикса. Хелпер админки `url()` разрешает
пути внутри её mount, а не отдельные маршруты ассетов приложения. Файлы установленного
пакета менять не нужно. При обновлении сверяйте свою копию базового шаблона с новой.
Она не может наследовать сама себя через `quite_admin/base.html`: это вызовет рекурсию.
Своя страница может наследовать встроенный base и добавлять собственный блок `head`.

## Плотность, типографика и поверхности

```css
/* admin-style/custom.css */
:root {
  --table-row-height: 40px; /* по умолчанию 44px */
  --control-height: 36px;  /* по умолчанию 38px */
  --text-title: 26px;      /* по умолчанию 28px */
  --radius-control: 4px;   /* по умолчанию 6px */
}

.operations-summary {
  padding: var(--space-6);
  color: var(--text);
  background: var(--paper);
  border: var(--border);
  border-radius: var(--radius);
}
```

| Токены | Назначение |
|---|---|
| `--text-xs`, `--text-sm`, `--text-base`, `--text-section`, `--text-title` | Шкала текста 12 / 13 / 14 / 16 / 28 px |
| `--space-1` … `--space-6`, `--space-8`, `--space-10` | Отступы 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 px |
| `--radius-sm`, `--radius-control`, `--radius` | Скругления 4 / 6 / 8 px |
| `--bg`, `--paper`, `--subtle`, `--hover` | Фон страницы, поверхность, вложенная область, наведение |
| `--text`, `--muted`, `--line`, `--border` | Основной и вспомогательный текст, разделители |
| `--accent`, `--accent-soft`, `--accent-border`, `--on-accent` | Действия и выбор |
| `--danger`, `--danger-soft`, `--danger-border`, `--on-danger` | Опасные действия и ошибки |

Системный шрифт можно сохранить; при необходимости используйте другой читаемый
локальный шрифт. Таблицы сохраняют выравнивание чисел и горизонтальную прокрутку
на узком экране. Менять токены удобнее, чем переопределять отдельные строки и подписи.

## Шаблоны и подписи полей

`ModelOptions(label=...)` меняет название коллекции. `FieldOptions(label=..., help_text=...)`
меняет подписи и подсказки без замены HTML. Параметр поля `template` заменяет отдельный
контрол; см. [расширения полей](extensions.md).

Свои экраны могут использовать `.page-heading`, `.panel`, `.form-section`, `.form-grid`,
`.form-footer`, `.record-list` и `.button.primary` / `.button.secondary`. Панель предназначена
для самостоятельного блока, секции — для групп внутри формы. Регистрация описана
в разделе [страниц и шаблонов](custom-pages.md).

При замене формы сохраняйте `__csrf`, `__revision`, `form_action`, имена полей, read-only
отображение, ошибки, подписи и `aria-describedby`. Оставляйте цикл `scripts` базового
шаблона для встроенного выбора связей. CSP разрешает CSS с того же origin и блокирует
inline-стили и внешние CDN. Переопределение CSS/шаблона не включает свой JavaScript.
Встроенные интерактивные компоненты получают только точные хеши своих скриптов.

После изменения темы проверьте список с активными фильтрами, длинную форму, ошибки
валидации и устаревшего редактирования, read-only запись и узкий экран. Проверьте
контраст текста, фокус клавиатуры и доступность последних полей под закреплённым footer.
