"""Order creation and processing."""
from __future__ import annotations

import uuid
from inventory.models import Order, Item
from inventory.pricing import calculate_discounted_price, calculate_total_with_tax


def create_order(
    customer_id: str,
    item: Item,
    quantity: int,
    disc_rate: float = 0.0,
) -> Order:
    """Create a new order for a customer.
    
    Needs validation: quantity must be greater than zero.
    """
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero")
    unit_price = calculate_discounted_price(item.price, discount_rate=disc_rate)
    subtotal = unit_price * quantity
    total = calculate_total_with_tax(subtotal)

    order_id = f"ord_{uuid.uuid4().hex[:8]}"
    return Order(
        id=order_id,
        customer_id=customer_id,
        item_id=item.id,
        quantity=quantity,
        total_price=round(total, 2),
    )
