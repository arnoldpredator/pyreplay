from cart import Cart


def load_orders():
    return [
        ("keyboard", 72.00, 2),
        ("mouse", 25.50, 6),
        ("monitor", 189.90, 1),
        ("cable", 4.75, 12),
    ]


def main():
    cart = Cart()
    for name, price, quantity in load_orders():
        cart.add(name, price, quantity)
    total = cart.total()
    print("items in cart:", len(cart.items))
    print("grand total:", round(total, 2))   # hand-checked: should be 527.70


if __name__ == "__main__":
    main()
