"""Sorting custom objects: each comparison secretly calls __lt__."""
class Card:
    def __init__(self, rank):
        self.rank = rank
    def __lt__(self, other):          # invoked implicitly by <, by sort()
        return self.rank < other.rank
    def __repr__(self):
        return "Card(%d)" % self.rank

hand = [Card(7), Card(3), Card(9), Card(1), Card(6)]
hand.sort()                           # drives __lt__ under the hood
print(hand)
