# Custom pages and templates

Provide a template directory and register a page:

```python
from quite_admin import Admin, Page

admin = Admin(auth=auth_backend, secret_key=session_secret, templates_dir="templates")

async def report_context(request):
    return {"orders": await reports.count_orders()}

admin.add_page(Page(
    slug="reports", title="Reports", template="reports.html", context=report_context,
    permission=can_access,
))
```

Create `templates/reports.html`:

```html
{% extends "quite_admin/base.html" %}
{% block content %}
  <h1>{{ page.title }}</h1>
  <p>Orders: {{ orders }}</p>
{% endblock %}
```

The authenticated page is available at `/admin/pages/reports` and appears in the menu.
Context callbacks may be synchronous or asynchronous; synchronous callbacks run in a worker thread.
Custom pages currently support GET requests only.

The shared context reserves `request`, `identity`, `csrf`, `url`, `admin`, `resources`,
`pages`, `title`, `description`, `language`, `theme`, `t` and `tn`.
Use `url("/models/orders/")` to generate a link with the correct mount prefix.
The base template inherits your [language and appearance](customization.md) settings.

## Override built-in screens

Place a template at the same relative path in your template directory.
For example, `templates/quite_admin/list.html` overrides the default list screen.
User templates take precedence over packaged templates.

No frontend build or external CDN is required for the admin interface.
The current Content Security Policy prohibits JavaScript. Additional interactive pages
require an explicit policy change in `SecurityHeaders` and appropriate asset routes.

The source checkout includes `examples/templates/report.html` and its context callback
in `examples/common.py` as a complete custom-page example.
