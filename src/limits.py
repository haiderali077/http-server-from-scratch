"""Explicit per-request memory limits."""
from typing import NamedTuple


class Limits(NamedTuple):
    header_bytes: int = 32768
    body_bytes: int = 1048576
