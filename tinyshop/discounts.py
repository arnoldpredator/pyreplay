def discounted(price, percent):
    """Price after a percentage discount."""
    return price - price * percent / 100


def bulk_discount(quantity):
    """Bigger orders earn bigger discounts."""
    if quantity >= 10:
        return 15
    if quantity >= 5:
        return 5
    return 0
