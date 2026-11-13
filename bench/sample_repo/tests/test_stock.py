from inventory.models import Item
from inventory.stock import StockTracker


def test_stock_tracker():
    tracker = StockTracker([Item(id="1", name="Pen", price=1.5, quantity=10)])
    assert tracker.get_stock("1") == 10
    tracker.update_quantity("1", -3)
    assert tracker.get_stock("1") == 7


def test_low_stock_detection():
    # Expects low_stock(tracker, threshold) or tracker.low_stock(threshold)
    from inventory import stock
    items = [
        Item(id="1", name="Low Item", price=10.0, quantity=3),
        Item(id="2", name="Ample Item", price=20.0, quantity=15),
    ]
    tracker = StockTracker(items)
    
    # Task 2: add low_stock function to inventory.stock
    low = stock.low_stock(tracker, threshold=5)
    assert len(low) == 1
    assert low[0].id == "1"
