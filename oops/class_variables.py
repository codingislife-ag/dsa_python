class Employee:

    raise_amount = 1.04
    num_of_emps = 0

    def __init__(self, first, last, pay):
        self.first = first
        self.last = last
        self.pay = pay
        self.email = first + '.' + last + '@company.com'

        # here it makes perfect sense to use Employee.num_of_emps instead of self.num_of_emps because the number of employees
        # will be same for everyone and it cant be different for any instance.
        Employee.num_of_emps += 1   
    

    def fullname(self):
        return f'{self.first} {self.last}'
    
    def apply_raise(self):
        # self.pay = int(self.pay * 1.04)
        # self.pay = int(self.pay * Employee.raise_amount)    -> we can also do this, but the result will vary if we try to 
        # change the value for raise_amount for a single employee, therefore the below one is preferred.

        self.pay = int(self.pay * self.raise_amount)    # this gives us the ability to change the value for a single instance
        # if we wanted to 
    

emp1 = Employee('Corey', 'Schafer', 50000)
emp2 = Employee('Test', 'User', 60000)
 
# print(emp_1.pay)
# emp_1.apply_raise()
# print(emp_1.pay)

# print(emp1.raise_amount)
# print(emp2.raise_amount)
# print(Employee.raise_amount)

# print(emp1.__dict__)             # This doesnt have the attribute raise_amount, it belongs to the class
# print(Employee.__dict__)


# Employee.raise_amount = 1.05
# print(emp1.raise_amount)
# print(emp2.raise_amount)
# print(Employee.raise_amount)   # class Employee namespace

emp1.raise_amount = 1.05
print(emp1.raise_amount)
print(emp2.raise_amount)
print(Employee.raise_amount)     # emp1's namespace
print(emp1.__dict__)



print(Employee.num_of_emps)