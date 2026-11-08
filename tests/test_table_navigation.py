import html
import json
import re
from types import SimpleNamespace

import pytest

from quite_admin.i18n import Translator


@pytest.mark.parametrize("language", ["en", "ru"])
def test_shared_table_pin_escapes_localized_accessible_labels(web_admin, language):
    resource = SimpleNamespace(slug="orders", label='Orders <script>"team"</script>')
    translations = Translator(language)
    rendered = web_admin.templates.env.get_template("quite_admin/_table_pin.html").render(
        resource=resource, t=translations.gettext
    )
    assert "<script>" not in rendered
    assert 'data-table-pin="orders"' in rendered
    for attribute in ("aria-label", "title"):
        value = html.unescape(re.search(rf'{attribute}="([^"]*)"', rendered)[1])
        assert value == translations.gettext("Pin table: {name}", name=resource.label)
    assert re.search(r"<button[^>]* hidden>", rendered)
    assert 'aria-pressed="false"' in rendered
    assert "data-table-pin-icon" in rendered
    assert "data-table-pin-notice" in rendered


def test_shared_rail_link_preserves_active_state_and_escapes_labels(web_admin):
    rail_link = web_admin.templates.env.get_template("quite_admin/_rail.html").module.rail_link
    label = 'Tables <script>"team"</script>'
    rendered = str(rail_link("/prefix/admin/", label, "home", True, "sidebar-home"))
    assert 'class="shell-nav-link sidebar-home active"' in rendered
    assert 'href="/prefix/admin/"' in rendered
    assert 'aria-current="page"' in rendered
    assert "<script>" not in rendered
    assert html.unescape(re.search(r'aria-label="([^"]*)"', rendered)[1]) == label
    assert 'class="shell-nav-icon"' in rendered
    assert "aria-current" not in str(rail_link("/schema", "Database schema", "schema"))


@pytest.mark.parametrize("language", ["en", "ru"])
def test_table_metadata_stays_hidden_and_home_catalog_renders_native_groups(web_admin, language):
    catalog = [
        {
            "id": "orders",
            "name": "orders",
            "label": "Orders <script>alert(1)</script>",
            "group": "Sales <team>",
            "url": "/admin/models/orders/",
        },
        {
            "id": "users",
            "name": "users",
            "label": "Users",
            "group": "People",
            "url": "/admin/models/users/",
        },
    ]
    template = web_admin.templates.env.get_template("quite_admin/_table_navigation.html")
    rendered = template.render(
        table_catalog=catalog,
        t=Translator(language).gettext,
        url=lambda path: "/admin/" if path == "/" else path,
    )
    assert "<script>" not in rendered
    metadata = re.search(r"data-catalog='([^']*)'", rendered)[1]
    assert json.loads(html.unescape(metadata)) == catalog
    metadata_tag = re.search(r"<div[^>]*data-table-directory[^>]*>", rendered)[0]
    assert " hidden" in metadata_tag
    assert "<nav" not in rendered and "<details" not in rendered
    assert "data-table-search " not in rendered
    assert 'role="option"' not in rendered and 'role="listbox"' not in rendered
    assert rendered.index("</div>") < rendered.index("<dialog")
    home = web_admin.templates.env.get_template("quite_admin/_table_catalog.html").render(
        table_catalog=catalog,
        t=Translator(language).gettext,
        url=lambda path: "/admin/",
    )
    assert "<script>" not in home
    assert "Orders &lt;script&gt;alert(1)&lt;/script&gt;" in home
    assert 'href="/admin/models/orders/"' in home
    assert "<code>orders</code>" in home
    assert 'data-table-link="orders"' in home
    assert 'data-group="Sales &lt;team&gt;"' in home
    assert 'data-group="People"' in home
    assert "data-home-catalog" in home
    assert all(" open" not in tag for tag in re.findall(r"<details[^>]*>", home))


def test_table_navigation_partial_handles_no_allowed_tables(web_admin):
    rendered = web_admin.templates.env.get_template("quite_admin/_table_navigation.html").render(
        table_catalog=[], t=Translator("en").gettext, url=lambda path: "/admin/"
    )
    assert "data-table-link=" not in rendered
    assert "data-catalog='[]'" in rendered
    home = web_admin.templates.env.get_template("quite_admin/_table_catalog.html").render(
        table_catalog=[], t=Translator("en").gettext, url=lambda path: "/admin/"
    )
    assert "No tables available." in home


def test_home_catalog_renders_every_authorized_table_without_truncation(web_admin):
    catalog = [
        {
            "id": f"table_{index}",
            "name": f"table_{index}",
            "label": f"Table {index}",
            "group": f"Group {index % 5}",
            "url": f"/admin/models/table_{index}/",
        }
        for index in range(1993)
    ]
    rendered = web_admin.templates.env.get_template("quite_admin/_table_catalog.html").render(
        table_catalog=catalog, t=Translator("en").gettext, url=lambda path: "/admin/"
    )
    assert rendered.count("data-table-link=") == 1993
    assert '<span class="badge">1993</span>' in rendered
    assert 'data-table-link="table_1992"' in rendered
    assert "<code>table_1992</code>" in rendered
