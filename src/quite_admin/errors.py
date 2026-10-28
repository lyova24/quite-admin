"""Public exceptions an adapter can raise without leaking database details."""


class AdminError(Exception):
    status_code = 400


class NotFound(AdminError):
    status_code = 404


class Conflict(AdminError):
    status_code = 409


class ValidationError(AdminError):
    status_code = 422

    def __init__(self, errors: dict[str, str]):
        self.errors = errors
        super().__init__("Please correct the highlighted fields.")
