"""Pricing and tax calculation utilities."""
from __future__ import annotations


def calculate_discounted_price(price: float, discount_rate: float) -> float:
    """Calculate price after applying discount rate."""
    if discount_rate < 0 or discount_rate > 1:
        raise ValueError("Discount rate must be between 0.0 and 1.0")
    return price * (1.0 - discount_rate)


def calculate_total_with_tax(subtotal: float, tax_rate: float = 0.08) -> float:
    """Add sales tax to subtotal."""
    return subtotal * (1.0 + tax_rate)
