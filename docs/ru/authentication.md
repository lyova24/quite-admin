# Авторизация и права

Авторизация обязательна. Есть локальный backend с scrypt-хешами:

```python
from quite_admin import PasswordAuth, hash_password
auth = PasswordAuth({"alice": hash_password(password_from_secret_store)})
# Для локального запуска: PasswordAuth.single_user("alice", password_from_secret_store)
```

Для пользователей из приложения реализуйте два async-метода:

```python
from quite_admin import Identity

class ApplicationAuth:
    async def authenticate(self, request, username, password):
        user = await accounts.verify_admin(username, password)
        if user:
            return Identity(str(user.id), user.name, frozenset(user.roles))
        return None

    async def get_identity(self, request, subject):
        user = await accounts.get_active_admin(subject)
        if user:
            return Identity(str(user.id), user.name, frozenset(user.roles))
        return None
```

`get_identity()` вызывается на каждом защищённом запросе: можно сразу отзывать доступ.
Пользователь доступен в `request.state.identity` и в шаблонах как `identity`.

Права проверяются и для кнопок, и для прямых запросов:

```python
async def can_access(request, identity, action):
    return "admin" in identity.roles or action in {"list", "view"}

admin.register(User, options=ModelOptions(permission=can_access))
```

Действия: `list`, `view`, `create`, `edit`, `delete`. Это права уровня коллекции.
Для tenant isolation и ограничений отдельных записей фильтруйте запросы в собственном
адаптере; одного скрытия элементов интерфейса недостаточно.

Сессии подписаны, HttpOnly, SameSite=Lax, Secure по умолчанию; `secure_cookies=False`
предназначен для локального HTTP. Секрет должен быть постоянным и общим для workers.
В подписанной cookie хранится subject и CSRF, а не пароль. Cookie не шифруется.
Logout удаляет cookie текущего браузера; он не отзывает скопированные cookies.
Для немедленного отзыва используйте `get_identity()` с серверным реестром сессий / версией доступа.

Все POST, включая login/logout, защищены CSRF. Jinja autoescape, CSP без JS,
ограничение тела формы в 1 MiB, запрет duplicate form fields и `Cache-Control: no-store`
включены. Login limiter: 10 попыток в минуту на IP внутри процесса.
Для нескольких workers настройте общий limiter на ingress/proxy.
При нескольких админках на одном домене задайте им разные `session_cookie`.
