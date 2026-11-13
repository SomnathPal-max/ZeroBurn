"""Warehouse stock management and tracking."""
from __future__ import annotations

from typing import Iterable
from inventory.models import Item


class StockTracker:
    def __init__(self, initial_items: Iterable[Item] | None = None) -> None:
        self.inventory: dict[str, Item] = {}
        if initial_items:
            for item in initial_items:
                self.inventory[item.id] = item

    def add_item(self, item: Item) -> None:
        self.inventory[item.id] = item

    def update_quantity(self, item_id: str, delta: int) -> int:
        if item_id not in self.inventory:
            raise KeyError(f"Item {item_id} not found in inventory")
        self.inventory[item_id].quantity += delta
        return self.inventory[item_id].quantity

    def get_stock(self, item_id: str) -> int:
        if item_id not in self.inventory:
            return 0
        return self.inventory[item_id].quantity

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]

def low_stock(tracker: StockTracker, threshold: int = 5) -> list[Item]:
    return [item for item in tracker.inventory.values() if item.quantity <= threshold]
