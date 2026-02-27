'''
Class methods are also called Alternative Constructors -> It means that it provides multiple ways to create our object.

Regular instance methods Vs Class Methods Vs Static Methods
Static Methods -> which dont operate on the instance or the class.
'''

class Employee:

    raise_amount = 1.04
    num_of_emps = 0

    def __init__(self, first, last, pay):
        self.first = first
        self.last = last
        self.pay = pay
        self.email = f'{first}.{last}@company.com'

        Employee.num_of_emps += 1

    def fullname(self):
        return f"{self.first} {self.last}"
    
    def apply_raise(self):
        self.pay = int(self.pay * self.raise_amount)

    @classmethod
    def set_raise_amount(cls, amount):
        cls.raise_amount = amount

    # acting as an alternative constructor, starting with 'from' is not necessary but its a convention
    @classmethod
    def from_string(cls, employee_string):
        first, last, pay = employee_string.split('-')
        return cls(first, last, pay)
    
    # static methods dont take instance or class as an argument, so if instance or class is not being used, thats your cue
    # to use static method instead of class method
    @staticmethod
    def is_workday(day):
        if day.weekday() == 5 or day.weekday() == 6:
            return False
        return True
    

import datetime

my_date = datetime.date(2016, 7, 11)
print(Employee.is_workday(my_date))


    
emp1 = Employee('Corey', 'Schafer', 50000)
emp2 = Employee('Test', 'Employee', 60000)

Employee.set_raise_amount(1.05)

# this will also work, but this doesnt make a lot of sense
emp1.set_raise_amount(1.05)       

# print(Employee.raise_amount)
# print(emp1.raise_amount)
# print(emp2.raise_amount)
    


emp_str_1 = "John-Doe-70000"
emp_str_2 = "Steve-Smith-30000"
emp_str_3 = "Jane-Doe-90000"

new_emp_1 = Employee.from_string(emp_str_1)
print(new_emp_1.email)
print(new_emp_1.pay)


# not needed anymore, as we have implemented the class method
# first, last, pay = emp_str_1.split('-')
# new_emp_1 = Employee(first, last, pay)
# print(new_emp_1.email)
# print(new_emp_1.pay)