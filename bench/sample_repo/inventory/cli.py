"""CLI utility for inventory queries."""
from __future__ import annotations

import argparse
from typing import Sequence
from inventory.models import Item


def list_items(items: Sequence[Item], limit: int | None = None) -> list[Item]:
    """List inventory items, optionally limited to `limit` items."""
    # When CLI flag --limit is wired, limit can be passed
    if limit is not None:
        return list(items[:limit])
    return list(items)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inventory CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # Task 6 needs --limit flag added here
    list_cmd = subparsers.add_parser("list", help="List all items")
    list_cmd.add_argument("--limit", type=int, default=None, help="Limit number of items")
    return parser
