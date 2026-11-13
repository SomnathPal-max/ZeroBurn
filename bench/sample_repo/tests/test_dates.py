from datetime import datetime
from inventory.dates import parse_order_date


def test_parse_iso_date():
    # Task 5: parse date formatted as YYYY-MM-DD
    dt = parse_order_date("2026-11-15")
    assert dt == datetime(2026, 11, 15)
