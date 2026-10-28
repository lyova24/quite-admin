# Authentication and permissions

Authentication is required. The built-in local backend uses salted scrypt password hashes:

```python
from quite_admin import PasswordAuth, hash_password

auth = PasswordAuth({"alice": hash_password(password_from_secret_store)})
# For a local demo: PasswordAuth.single_user("alice", password_from_secret_store)
```

## Use application accounts

Implement two asynchronous methods to connect your account service:

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

`get_identity()` runs on every protected request, allowing immediate access revocation.
The current identity is available as `request.state.identity` and as `identity` in templates.

## Authorize operations

Permissions apply to both rendered controls and direct requests:

```python
async def can_access(request, identity, action):
    return "admin" in identity.roles or action in {"list", "view"}

admin.register(User, options=ModelOptions(permission=can_access))
```

Actions are `list`, `view`, `create`, `edit` and `delete`.
These permissions apply to an entire collection. Implement row filtering and tenant
isolation inside a custom adapter; hiding a button does not constrain its underlying query.

## Sessions

Cookies are signed, HttpOnly, SameSite=Lax and Secure by default.
Set `secure_cookies=False` for local HTTP only. Use a persistent random secret of at least
32 bytes, shared by all workers. The cookie contains a subject and CSRF token, not a password;
its contents are signed but not encrypted.

Logout removes the current browser's cookie. It does not invalidate previously copied cookies.
For immediate revocation, check a server-side session registry or access version in
`get_identity()`. Give separate admins on the same domain different `session_cookie` names.

## Request protection

All POST requests, including login and logout, require CSRF validation.
The admin enables Jinja autoescaping, a Content Security Policy without JavaScript,
a 1 MiB form-body limit, duplicate-field rejection and `Cache-Control: no-store`.

The bounded login limiter permits 10 attempts per minute per client IP within one process.
Use a shared ingress or reverse-proxy limiter for multi-worker deployments.
