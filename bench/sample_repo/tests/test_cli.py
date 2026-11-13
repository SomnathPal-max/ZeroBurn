from inventory.cli import build_parser, list_items
from inventory.models import Item


def test_cli_limit_argument():
    parser = build_parser()
    args = parser.parse_args(["list", "--limit", "3"])
    assert args.limit == 3


def test_list_items_with_limit():
    items = [Item(id=str(i), name=f"Item {i}", price=1.0) for i in range(10)]
    limited = list_items(items, limit=3)
    assert len(limited) == 3
