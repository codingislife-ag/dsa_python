# class InventoryItem:

#     def __init__(self, name: str, unit_price: float, quantity_on_hand: int = 0):
#         self.name = name
#         self.unit_price = unit_price
#         self.quantity_on_hand = quantity_on_hand

#     def __repr__(self):
#         return f"InventoryItem(name={self.name!r}, unit_price={self.unit_price!r}, quantity_on_hand={self.quantity_on_hand!r})"

#     def __eq__(self, other):
#         if not isinstance(other, InventoryItem):
#             return False
#         return (
#             self.name == other.name and
#             self.unit_price == other.unit_price and
#             self.quantity_on_hand == other.quantity_on_hand
#         )
# Equivalent class without using dataclass

# https://docs.python.org/3/library/dataclasses.html#class-variables


from dataclasses import dataclass, field

@dataclass
class InventoryItem:
    """
    Class for keeping track on an item in Inventory
    """

    # without dataclass these would just be metadata
    name: str
    unit_price: float 
    quantity_on_hand: int = 0
    sizes: list[str] =field(default_factory=list)

    def total_cost(self) -> float:
        return self.unit_price * self.quantity_on_hand
    

def func(lst=[]):
    lst.append(1)
    print(lst)

func()
func()