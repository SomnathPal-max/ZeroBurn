"""Inventory data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Item:
    id: str
    name: str
    price: float
    quantity: int = 0
    category: str = "general"


@dataclass
class Customer:
    id: str
    name: str
    email: str


@dataclass
class Order:
    id: str
    customer_id: str
    item_id: str
    quantity: int
    total_price: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
