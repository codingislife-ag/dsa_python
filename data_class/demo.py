class Point:

    # They are type annotations, not actual class variables and not actual instance variables.
    # They do NOT create storage.
    # They only tell Python (and type checkers) that:
    # "Instances of this class are expected to have attributes x and y of type int."
    
    x: int
    y: int

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __repr__(self):
        return f"Point(x={self.x}, y={self.y})"
    
    def __eq__(self, p: Point) -> bool:
        return self.x == p.x and self.y == p.y
    
p1 = Point(1, 2)
p2 = Point(2, 1)
print(p1, p2)
print(p1 == p2)
