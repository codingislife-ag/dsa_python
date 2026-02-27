'''
dunder -> double underscore like __init__

https://docs.python.org/3/reference/datamodel.html#special-method-names

refer to datatime module for better real world practical examples

also check 'NotImplemented'
'''

class Employee:

    raise_amount = 1.04

    def __init__(self, first, last, pay):
        self.first = first 
        self.last = last
        self.pay = pay
        self.email = f"{first}.{last}@company.com"

    def fullname(self):
        return f"{self.first} {self.last}"
    
    def apply_raise(self):
        self.pay = int(self.pay * self.raise_amount)
    
    def __repr__(self):
        return f"Employee('{self.first}', '{self.last}', {self.pay})"

    def __str__(self):
        return f"{self.fullname()} - {self.email}"
    
    def __add__(self, other):
        return self.pay + other.pay
    
    def __len__(self):
        return len(self.fullname())


emp1 = Employee('Corey', 'Schafer', 50000)
emp2 = Employee('Test', 'Employee', 60000)

# print(emp1 + emp2)

print(len('test'))
print('test'.__len__())

print(len(emp1))

# print(emp1)
# print(repr(emp1))
# print(str(emp1))

# print(emp1.__repr__())
# print(emp1.__str__())
    

# print(1 + 2)
# print(int.__add__(1, 2))

# print(str.__add__('a', 'b'))
