"""SQL integer ranges shared with the isolated SQLAlchemy 1.3 adapter."""

from sqlalchemy import BigInteger, Integer, SmallInteger


def integer_bounds(type_):
    if not isinstance(type_, Integer):
        return {}
    name = type(type_).__name__.upper()
    bits = {"TINYINT": 8, "MEDIUMINT": 24}.get(name, 32)
    if isinstance(type_, BigInteger):
        bits = 64
    elif isinstance(type_, SmallInteger):
        bits = 16
    if getattr(type_, "unsigned", False):
        return {"minimum": 0, "maximum": 2**bits - 1}
    return {"minimum": -(2 ** (bits - 1)), "maximum": 2 ** (bits - 1) - 1}
