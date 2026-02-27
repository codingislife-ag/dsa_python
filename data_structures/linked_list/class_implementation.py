class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

class LinkedList:
    def __init__(self):
        self.head = None
        self._size = 0

    def __len__(self):
        return self._size
    
    def is_empty(self):
        return self.head is None
    
    def insert_at_beginning(self, data):
        new_node = Node(data)
        new_node.next = self.head
        self.head = new_node
        self._size += 1

    def insert_at_end(self, data):
        new_node = Node(data)

        if(self.is_empty()):
            self.head = new_node
            self._size += 1
            return
        
        current = self.head
        while(current.next):
            current = current.next
        
        current.next = new_node
        self._size += 1

    def delete(self):
        pass