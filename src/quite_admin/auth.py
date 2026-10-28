from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Protocol

from anyio import to_thread
from starlette.requests import Request


@dataclass(frozen=True)
class Identity:
    subject: str
    display_name: str = ""
    roles: frozenset[str] = frozenset()


class AuthBackend(Protocol):
    async def authenticate(
        self, request: Request, username: str, password: str
    ) -> Identity | None: ...
    async def get_identity(self, request: Request, subject: str) -> Identity | None: ...


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("An empty admin password is not allowed.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


class PasswordAuth:
    """A small local account backend. Values are scrypt hashes, never plaintext passwords."""

    def __init__(self, users: Mapping[str, str]) -> None:
        if not users or any(
            not name or not value.startswith("scrypt$") for name, value in users.items()
        ):
            raise ValueError("Provide named users with hashes produced by hash_password().")
        self.users = dict(users)
        self._dummy = hash_password(secrets.token_urlsafe(32))

    @classmethod
    def single_user(cls, username: str, password: str) -> PasswordAuth:
        return cls({username: hash_password(password)})

    async def authenticate(self, request: Request, username: str, password: str) -> Identity | None:
        encoded = self.users.get(username, self._dummy)
        valid = await to_thread.run_sync(verify_password, password, encoded)
        return Identity(username, username) if valid and username in self.users else None

    async def get_identity(self, request: Request, subject: str) -> Identity | None:
        # Recheck on every request so deleted accounts immediately lose access.
        return Identity(subject, subject) if subject in self.users else None


class LoginThrottle:
    """Bounded, per-process throttling. Use a shared reverse-proxy limiter across workers."""

    def __init__(self, attempts: int = 10, window: int = 60, max_clients: int = 4096) -> None:
        self.attempts = attempts
        self.window = window
        self.max_clients = max_clients
        self._clients: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def attempt(self, client: str) -> int:
        now = monotonic()
        start, count = self._clients.pop(client, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        self._clients[client] = (start, count + 1)
        if len(self._clients) > self.max_clients:
            self._clients.popitem(last=False)
        return max(1, int(self.window - (now - start))) if count >= self.attempts else 0

    def reset(self, client: str) -> None:
        self._clients.pop(client, None)
