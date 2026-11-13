"""In-memory inventory database storage."""
from __future__ import annotations

from inventory.models import Item, Customer, Order


class InventoryStore:
    def __init__(self) -> None:
        self.items: dict[str, Item] = {}
        self.customers: dict[str, Customer] = {}
        self.orders: dict[str, Order] = {}

    def save_item(self, item: Item) -> None:
        self.items[item.id] = item

    def get_item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def save_customer(self, customer: Customer) -> None:
        self.customers[customer.id] = customer

    def get_customer(self, customer_id: str) -> Customer | None:
        return self.customers.get(customer_id)

    def save_order(self, order: Order) -> None:
        self.orders[order.id] = order

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)
