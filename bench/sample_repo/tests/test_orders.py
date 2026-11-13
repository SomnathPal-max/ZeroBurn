import pytest
from inventory.models import Item
from inventory.orders import create_order


def test_create_order_success():
    item = Item(id="item1", name="Book", price=20.0, quantity=5)
    order = create_order(customer_id="cust1", item=item, quantity=2)
    assert order.quantity == 2
    assert order.total_price > 0


def test_create_order_zero_quantity_raises_value_error():
    item = Item(id="item1", name="Book", price=20.0, quantity=5)
    # Task 4: quantity <= 0 must raise ValueError
    with pytest.raises(ValueError, match="Quantity must be greater than zero"):
        create_order(customer_id="cust1", item=item, quantity=0)
