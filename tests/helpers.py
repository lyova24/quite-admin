import html
import re


def csrf(response) -> str:
    token = re.search(r'name="__csrf" value="([^"]+)"', response.text)
    assert token is not None, response.text
    return html.unescape(token.group(1))


async def login(client, prefix="/admin"):
    form = await client.get(prefix + "/login")
    assert form.status_code == 200, form.text
    result = await client.post(
        prefix + "/login",
        data={
            "__csrf": csrf(form),
            "username": "admin",
            "password": "correct horse battery staple",
        },
    )
    assert result.status_code == 303, result.text
    assert result.headers["location"] == prefix + "/"
    return result
