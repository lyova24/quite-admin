# Свои страницы и шаблоны

```python
from quite_admin import Admin, Page

admin = Admin(auth=auth_backend, secret_key=session_secret, templates_dir="templates")

async def report_context(request):
    return {"orders": await reports.count_orders()}

admin.add_page(Page(
    slug="reports", title="Отчёты", template="reports.html", context=report_context,
    permission=can_access,
))
```

`templates/reports.html`:

```html
{% extends "quite_admin/base.html" %}
{% block content %}
  <h1>{{ page.title }}</h1>
  <p>Заказов: {{ orders }}</p>
{% endblock %}
```

Страница доступна по `/admin/pages/reports`, защищена авторизацией и появляется
в меню. Поддерживаются sync/async context callbacks; синхронные выполняются в worker thread.
Свои страницы пока поддерживают только GET. Ключи `template_api_version`, `resource_groups`, `request`, `identity`, `csrf`,
`url`, `admin`, `resources`, `pages`, `scripts`, `title`, `description`, `language`, `theme`, `logo_url`, `breadcrumbs`, `t` и `tn`
зарезервированы общим контекстом. Базовый шаблон наследует настройки
[языка и оформления](customization.md).
Навигационная цепочка содержит ссылки на обзор, таблицу и родительскую запись с учётом
mount/proxy. Текущая страница помечается `aria-current="page"`.

Чтобы изменить встроенный экран, разместите свой шаблон по тому же пути,
например `templates/quite_admin/list.html`. Внешние CDN и сборка frontend не нужны.
На авторизованных страницах разрешается встроенный скрипт навигации для настроек
боковой панели и групп. Встроенные компоненты получают точные
SHA-256 и SRI для своих скриптов только на необходимых экранах. Inline-скрипты
и произвольные скрипты с того же origin остаются запрещены; свои страницы
не наследуют разрешения скриптов полей, фильтров и схемы.

Значения callback с именами `request`, `template`, `page`, `status` и `trusted_scripts`
игнорируются: данные приложения не заменяют аргументы рендера. Гарантированные
блоки и контексты описаны в [контракте шаблонов API 1](api-stability.md).
