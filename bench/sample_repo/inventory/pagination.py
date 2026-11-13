"""Pagination helper for listing items and orders."""
from __future__ import annotations

from typing import TypeVar, Sequence

T = TypeVar("T")


def paginate(items: Sequence[T], page: int = 1, page_size: int = 10) -> list[T]:
    """Return slice of items for given 1-based page and page_size."""
    if page < 1:
        raise ValueError("Page must be >= 1")
    if page_size < 1:
        raise ValueError("Page size must be >= 1")

    # BUG: Off-by-one error (+1 incorrectly shifts start index)
    start = (page - 1) * page_size
    end = start + page_size
    return list(items[start:end])
