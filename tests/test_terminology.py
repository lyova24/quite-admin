import pytest
from httpx import ASGITransport, AsyncClient

from quite_admin import Admin, ModelOptions
from quite_admin.i18n import Translator

from .helpers import login


@pytest.mark.parametrize(
    ("language", "tables", "open_table", "all_tables", "empty_table"),
    [
        ("en", "Tables", "Open table", "All tables", "This table has no records yet."),
        ("ru", "Таблицы", "Открыть таблицу", "Все таблицы", "В этой таблице пока нет записей."),
    ],
)
async def test_table_wording_preserves_model_routes_and_history_filter_keys(
    auth, web_backend, language, tables, open_table, all_tables, empty_table
):
    adapter, model = web_backend
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        adapters=[adapter],
        language=language,
    )
    admin.register(model, options=ModelOptions(label="Items"))
    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        await login(client, "")
        home = await client.get("/")
        assert f'aria-label="{tables}"' in home.text
        assert admin.gettext("Find a table") in home.text
        assert 'href="/models/items/"' in home.text
        listing = await client.get("/models/items/")
        assert empty_table in listing.text
        history = await client.get("/history?collection=items")
        assert history.status_code == 200
        assert f">{all_tables}</option>" in history.text
        assert 'name="collection"' in history.text
        assert 'value="items" selected' in history.text
        graph = await client.get("/schema")
        assert open_table in graph.text


@pytest.mark.parametrize("language", ["en", "ru"])
def test_legacy_template_messages_use_current_table_wording(language):
    translator = Translator(language)
    for old, current in (
        ("Collection", "Table"),
        ("Collections", "Tables"),
        ("COLLECTIONS", "TABLES"),
        ("Other collections", "Other tables"),
        ("Open collection", "Open table"),
        ("No collections yet", "No tables yet"),
        ("This collection has no records yet.", "This table has no records yet."),
    ):
        assert translator.gettext(old) == translator.gettext(current)
        assert "collection" not in translator.gettext(old).lower()
        assert "коллекц" not in translator.gettext(old).lower()
    for count in (1, 2, 5, 11, 21):
        assert translator.ngettext("collection", "collections", count) == translator.ngettext(
            "table", "tables", count
        )
    assert translator.gettext("My custom collection") == "My custom collection"
