"""Order date parsing utilities."""
from __future__ import annotations

from datetime import datetime


def parse_order_date(date_str: str) -> datetime:
    """Parse order date string in format YYYY-MM-DD.
    
    BUG: Incorrect format string '%Y/%m/%d' instead of '%Y-%m-%d'.
    """
    return datetime.strptime(date_str.strip(), "%Y-%m-%d")
