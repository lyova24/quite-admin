import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from litestar import Litestar, Router

from quite_admin import Admin, Field, ModelOptions, ModelSchema, Page, Theme
from quite_admin.errors import ValidationError

from .helpers import csrf, login, revision


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_localized_crud_and_theme_with_nested_mounts(auth, backend, framework):
    adapter, model = backend
    russian = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        session_cookie="ru_admin",
        adapters=[adapter],
        language="ru",
        title="Управление магазином",
        description="Товары и заказы в одном месте.",
        theme=Theme(
            primary="#2563eb",
            background="#0f172a",
            surface="#172033",
            text="#e2e8f0",
            muted="#94a3b8",
            border="#334155",
        ),
    )
    russian.register(model, options=ModelOptions(readonly_fields=("count",), exclude=("internal",)))
    english = Admin(
        auth=auth,
        secret_key="e" * 32,
        secure_cookies=False,
        session_cookie="en_admin",
    )
    if framework == "fastapi":
        child = FastAPI()
        russian.mount_fastapi(child, "/russian")
        english.mount_fastapi(child, "/english")
        host = FastAPI()
        host.mount("/internal", child)
    else:
        host = Litestar(
            route_handlers=[
                Router(
                    path="/internal",
                    route_handlers=[
                        russian.litestar_route("/russian"),
                        english.litestar_route("/english"),
                    ],
                )
            ]
        )
    prefix = "/proxy/internal/russian"
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        ru_form, en_form = await asyncio.gather(
            client.get(prefix + "/login"), client.get("/proxy/internal/english/login")
        )
        assert '<html lang="ru">' in ru_form.text
        assert "Имя пользователя" in ru_form.text
        assert "Пароль" in ru_form.text
        assert "Управление магазином" in ru_form.text
        assert "Товары и заказы в одном месте." in ru_form.text
        assert '<html lang="en">' in en_form.text
        assert "Username" in en_form.text
        assert "Имя пользователя" not in en_form.text
        assert 'href="' + prefix + '/theme.css"' in ru_form.text
        assert "<style" not in ru_form.text and "style=" not in ru_form.text
        assert "style-src 'self'" in ru_form.headers["content-security-policy"]
        ru_css = await client.get(prefix + "/theme.css")
        en_css = await client.get("/proxy/internal/english/theme.css")
        assert ru_css.status_code == 200
        assert ru_css.headers["content-type"].startswith("text/css")
        assert ru_css.headers["cache-control"] == "no-store"
        assert "--accent:#2563eb" in ru_css.text
        assert "--bg:#0f172a" in ru_css.text
        assert "--paper:#172033" in ru_css.text
        assert "--accent:#3e6656" in en_css.text
        assert "#2563eb" not in en_css.text

        bad = await client.post(
            prefix + "/login",
            data={"__csrf": csrf(ru_form), "username": "admin", "password": "wrong"},
        )
        assert bad.status_code == 401
        assert "Неверное имя пользователя или пароль." in bad.text
        await login(client, prefix)
        dashboard = await client.get(prefix + "/")
        assert "1 коллекция" in dashboard.text
        assert "Управление магазином" in dashboard.text
        assert "Товары и заказы в одном месте." in dashboard.text
        assert "Открыть коллекцию" in dashboard.text

        form = await client.get(prefix + "/models/items/new")
        assert "Создать запись" in form.text
        assert "Только чтение" in form.text
        assert "Поля записи" in form.text
        assert "Неизменяемые поля" in form.text
        assert 'value="true"' in form.text  # Only labels are translated, never stored values.
        data = {"__csrf": csrf(form), "name": "Search", "active": "true", "note": ""}
        invalid = await client.post(prefix + "/models/items/new", data={**data, "active": "maybe"})
        assert invalid.status_code == 422
        assert "Выберите «Да» или «Нет»." in invalid.text
        max_length = adapter.describe(model).by_name["name"].max_length
        invalid = await client.post(
            prefix + "/models/items/new", data={**data, "name": "x" * (max_length + 1)}
        )
        assert invalid.status_code == 422
        assert f"Используйте не более {max_length} символов." in invalid.text
        invalid = await client.post(prefix + "/models/items/new", data={**data, "count": "3"})
        assert invalid.status_code == 422
        assert "Это поле недоступно для записи." in invalid.text

        created = await client.post(prefix + "/models/items/new", data=data)
        assert created.status_code == 303, created.text
        detail_url = created.headers["location"]
        detail = await client.get(detail_url)
        assert "Сохранить изменения" in detail.text
        assert "Search" in detail.text  # Application values do not pass through the catalog.
        assert 'name="note" value=""' in detail.text
        assert ">Да<" in detail.text
        listing = await client.get(prefix + "/models/items/")
        assert "1 запись" in listing.text
        assert "Поиск записей…" in listing.text
        conflict = await client.post(prefix + "/models/items/new", data=data)
        assert conflict.status_code == 409
        assert "Операция нарушает ограничение базы данных." in conflict.text

        edit = await client.get(detail_url)
        assert "Сохранить изменения" in edit.text
        edited = await client.post(
            detail_url,
            data={
                **data,
                "__csrf": csrf(edit),
                "__revision": revision(edit),
                "active": "false",
                "note": "Изменено",
            },
        )
        assert edited.status_code == 303
        assert "Изменено" in (await client.get(detail_url)).text
        denied = await client.post(detail_url, data={**data, "__csrf": "wrong"})
        assert denied.status_code == 403
        assert "Недействительный CSRF-токен." in denied.text
        confirmation = await client.get(detail_url + "/delete")
        assert "Удалить эту запись?" in confirmation.text
        deleted = await client.post(detail_url + "/delete", data={"__csrf": csrf(confirmation)})
        assert deleted.status_code == 303
        missing = await client.get(detail_url)
        assert missing.status_code == 404
        assert "Запись не найдена." in missing.text
        assert "0 записей" in (await client.get(prefix + "/models/items/")).text


async def test_branding_and_custom_page_context_are_escaped_and_inherited(auth, tmp_path):
    (tmp_path / "report.html").write_text(
        '{% extends "quite_admin/base.html" %}{% block content %}'
        "<h1>{{ page.title }}</h1><p>{{ t('Search') }}</p>"
        "<p>{{ tn('record', 'records', 21) }}</p>"
        "<p>{{ language }} {{ theme.primary }}</p>{% endblock %}"
    )
    admin = Admin(
        auth=auth,
        secret_key="s" * 32,
        secure_cookies=False,
        language="ru",
        title='<script>alert("name")</script>',
        description='<img src=x onerror="alert(1)"> {description}',
        theme=Theme(primary="#ABC"),
        templates_dir=tmp_path,
    )
    admin.add_page(
        Page(
            "report",
            "Мой отчёт",
            "report.html",
            context=lambda request: {"language": "en", "title": "Override", "t": None},
        )
    )
    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        form = await client.get("/login")
        assert "&lt;script&gt;" in form.text
        assert "&lt;img" in form.text
        assert "{description}" in form.text
        assert "<script>" not in form.text and "<img" not in form.text
        await login(client, "")
        page = await client.get("/pages/report")
        assert page.status_code == 200
        assert "Мой отчёт" in page.text and ">Найти<" in page.text
        assert ">запись<" in page.text and "ru #aabbcc" in page.text
        assert '<html lang="ru">' in page.text
        assert "Override" not in page.text


@pytest.mark.parametrize(
    ("count", "word"),
    [
        (0, "записей"),
        (1, "запись"),
        (2, "записи"),
        (5, "записей"),
        (11, "записей"),
        (21, "запись"),
        (22, "записи"),
        (25, "записей"),
    ],
)
def test_russian_record_counts(auth, count, word):
    admin = Admin(auth=auth, secret_key="s" * 32, language="ru")
    assert admin.ngettext("record", "records", count) == word


@pytest.mark.parametrize("color", ["red", "#abcd", "#12345g", "#fff;}body{display:none}"])
def test_theme_rejects_invalid_colors(color):
    with pytest.raises(ValueError, match="#RGB or #RRGGBB"):
        Theme(primary=color)


def test_unknown_language_is_rejected(auth):
    with pytest.raises(ValueError, match="language must be"):
        Admin(auth=auth, secret_key="s" * 32, language="de")


@pytest.mark.parametrize("framework", ["fastapi", "litestar"])
async def test_custom_logo_is_served_safely_under_a_proxy_prefix(auth, tmp_path, framework):
    image = tmp_path / "logo.svg"
    image.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><circle r="10"/></svg>'
    )
    admin = Admin(auth=auth, secret_key="s" * 32, logo=image, secure_cookies=False)
    host = FastAPI() if framework == "fastapi" else Litestar()
    if framework == "fastapi":
        admin.mount_fastapi(host, "/control")
    else:
        admin.mount_litestar(host, "/control")
    async with AsyncClient(
        transport=ASGITransport(app=host, root_path="/proxy"), base_url="http://test"
    ) as client:
        page = await client.get("/proxy/control/login")
        assert 'src="/proxy/control/logo"' in page.text
        logo = await client.get("/proxy/control/logo?path=pyproject.toml")
        assert logo.status_code == 200 and logo.text == image.read_text()
        assert logo.headers["content-type"] == "image/svg+xml"
        assert logo.headers["x-content-type-options"] == "nosniff"
        assert "script-src 'none'" in logo.headers["content-security-policy"]


def test_logo_configuration_rejects_missing_files_and_non_images(auth, tmp_path):
    (tmp_path / "config.txt").write_text("not an image")
    for path in (tmp_path / "missing.svg", tmp_path / "config.txt"):
        with pytest.raises(ValueError, match="logo must be"):
            Admin(auth=auth, secret_key="s" * 32, logo=path)


async def test_default_screens_have_no_unsolicited_descriptions(auth):
    admin = Admin(auth=auth, secret_key="s" * 32, language="ru", secure_cookies=False)
    async with AsyncClient(transport=ASGITransport(app=admin), base_url="http://test") as client:
        initial = await client.get("/login")
        assert 'class="subtitle"' not in initial.text
        assert "Войдите в рабочее пространство" not in initial.text
        await login(client, "")
        home = await client.get("/")
        for unwanted in (
            "ВАШЕ РАБОЧЕЕ ПРОСТРАНСТВО",
            "Просматривайте коллекции",
            "Готовы к работе",
        ):
            assert unwanted not in home.text


@pytest.mark.parametrize(("python_type", "kind"), [(int, "integer"), (dict, "json")])
def test_invalid_typed_values_have_localizable_errors(auth, python_type, kind):
    admin = Admin(auth=auth, secret_key="s" * 32, language="ru")
    schema = ModelSchema(
        "objects", (Field("id", int, primary_key=True), Field("value", python_type))
    )
    with pytest.raises(ValidationError) as result:
        ModelOptions().parse_values(schema, {"id": "1", "value": "private invalid input"}, True)
    error = admin.gettext(result.value.errors["value"])
    assert error == f"Введите корректное значение (тип: {kind})."
    assert "private invalid input" not in error
