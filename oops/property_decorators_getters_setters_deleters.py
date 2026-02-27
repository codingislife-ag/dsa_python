class Employee:

    def __init__(self, first, last):
        self.first = first 
        self.last = last
        # self.email = f"{first}.{last}@company.com". # this creates a problem when someone updates any value using emp1.first = 'Jim'(for example)

    @property
    def email(self):
        return f"{self.first}.{self.last}@company.com"
    
    @property
    def fullname(self):
        return f"{self.first} {self.last}"
    
    @fullname.setter
    def fullname(self, name):
        first, last = name.split(' ')
        self.first = first
        self.last = last

    @fullname.deleter
    def fullname(self):
        print('Delete Name!')
        self.first = None
        self.last = None
    


emp1 = Employee('John', 'Smith')

emp1.first = 'Jim'
emp1.fullname = 'Corey Schafer'

print(emp1.first)

# this will also force the users who are using this class to change their code. 
# previously we were using emp1.email, now we are doing emp1.email()  --> because we have converted this into a method
# so now next task is to use property decorator so all the users wont have to change their code and we can access the email
# using emp1.email
# print(emp1.email()).  # -> this is not needed after using property decorator
#same thing we can do with the full name

print(emp1.email)

# this is also not needed after using property decorator, no need to treat it as a method, we can just treat it as an attribute
# print(emp1.fullname())

print(emp1.fullname)

del emp1.fullname

