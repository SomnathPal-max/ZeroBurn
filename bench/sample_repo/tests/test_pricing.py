from inventory.pricing import calculate_discounted_price, calculate_total_with_tax


def test_pricing_with_named_parameter():
    # Expects discount_rate (renamed from disc_rate in Task 3)
    price = calculate_discounted_price(100.0, discount_rate=0.2)
    assert price == 80.0


def test_sales_tax():
    total = calculate_total_with_tax(100.0, tax_rate=0.05)
    assert total == 105.0
