class BankAccount:

    def __init__(self, balance):
        self.__balance = balance  # private variable

    def deposit(self, amount):
        self.__balance += amount
    
    def get_balance(self):
        return self.__balance
    

acc = BankAccount(1000)
bal = acc.get_balance()
print(bal)