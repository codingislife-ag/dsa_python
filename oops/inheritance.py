'''
Method Resolution Order
help(Class_Name)
isinstance()
issubclass()
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

class Developer(Employee):
    raise_amount = 1.10

    def __init__(self, first, last, pay, prog_lang):
        super().__init__(first, last, pay)
        # print(super)
        # print(super())
        # this is also correct, below line
        # Employee.__init__(self, first, last, pay)
        self.prog_lang = prog_lang

class Manager(Employee):

    def __init__(self, first: str, last: str, pay: int, employees: list[Employee] = None):
        super().__init__(first, last, pay)
        if employees == None:
            self.employees = []
        else:
            self.employees = employees

    def add_employee(self, emp):
        if emp not in self.employees:
            self.employees.append(emp)

    def remove_employee(self, emp):
        if emp in self.employees:
            self.employees.remove(emp)

    def print_employees(self):
        for emp in self.employees:
            print('-->', emp.fullname())


dev1 = Developer('Corey','Schafer', 50000, 'Python')
dev2 = Developer('Test', 'Employee', 60000, 'Java')

mgr1 = Manager('Sue', 'Smith', 90000, [dev1])
# print(mgr1.email)

# mgr1.add_employee(dev2)
# mgr1.remove_employee(dev1)
# mgr1.print_employees()

print(isinstance(mgr1, Manager))
print(isinstance(mgr1, Employee))
print(isinstance(mgr1, Developer))

print(issubclass(Developer, Employee))
print(issubclass(Manager, Employee))
print(issubclass(Manager, Developer))



# # print(help(Developer))

# print(dev1.email)
# print(dev1.prog_lang)
