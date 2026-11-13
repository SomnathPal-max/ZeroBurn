"""Confidential proprietary pricing algorithm."""

def proprietary_volatility_formula(strike: float, spot: float, time_to_exp: float) -> float:
    # Proprietary alpha coefficient
    alpha = 0.0425
    spread = abs(spot - strike)
    return (spread * alpha) / (time_to_exp ** 0.5)
