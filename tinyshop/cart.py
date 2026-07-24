from discounts import discounted, bulk_discount


class Cart:
    def __init__(self):
        self.items = []
        self.history = []

    def add(self, name, price, quantity):
        self.items.append((name, price, quantity))

    def total(self):
        amount = 0
        for name, price, quantity in self.items:
            percent = bulk_discount(quantity)
            line = discounted(price, percent) * quantity
            amount = line
            self.history.append(round(amount, 2))
        return amount
