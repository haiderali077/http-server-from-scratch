"""Explicit per-request memory limits."""
from typing import NamedTuple


class Limits(NamedTuple):
    header_bytes: int = 32768
    body_bytes: int = 1048576


class Timeouts(NamedTuple):
    header: float = 5.0
    body: float = 10.0
    write: float = 5.0
    idle: float = 2.0
