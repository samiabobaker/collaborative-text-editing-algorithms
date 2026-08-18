from typing import Literal

from unique_char.uniquechar import UniqueChar


class FugueTree:

    __node_counter: int = 1

    @staticmethod
    def get_next_node_id() -> int:
        id = FugueTree.__node_counter
        FugueTree.__node_counter += 1
        return id


    node_id: int

    #left_children: list[FugueTreeNode] - The root will never have left children.
    right_children: list[FugueTreeNode]

    __nodes: dict[int, FugueTreeNode]

    count: int # Not including tombstones

    def __init__(self):
        self.right_children = []
        self.node_id = 0 
        self.count = 0
        self.__nodes = {}

    def __get_node_at_index_without_tombstones(self, index: int) -> FugueTreeNode:
        if index < 0 or index >= self.count:
            raise IndexError()
        
        current_count = 0

        #for node in self.left_children:  
        #    if current_count + node.count >= index:
        #        return node.get_node_at_index_without_tombstones(index - current_count)
        #    current_count += node.count
        
        for node in self.right_children:  
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count
        
        raise IndexError()

    def __get_node_with_id(self, id: int) -> FugueTreeNode:
        return self.__nodes[id]
    
    def add_to_counts_of_node_with_id(self, node_id: int, node_count: int, tombstone_count: int):
        while node_id != 0:
            node = self.__get_node_with_id(node_id)
            node.count += node_count
            node.tombstone_count += tombstone_count
            node_id = node.parent_node_id

        self.count += node_count

    def traverse(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        #for node in self.left_children:
        #    result += node.traverse()
        
        for node in self.right_children:
            result += node.traverse()

        return result
    
    def traverse_with_tombstones(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        #for node in self.left_children:
        #    result += node.traverse()
        
        for node in self.right_children:
            result += node.traverse_with_tombstones()

        return result

    def insert_char(self, position: int, char: UniqueChar) -> FugueTreeNode:
        if position < 0 or position > self.count:
            raise IndexError()
                
        if position == 0:
            if len(self.right_children) == 0:
                node = FugueTreeNode(self, FugueTree.get_next_node_id(), char, self.node_id, 'right')
                self.right_children.append(node)
                self.__nodes[node.node_id] = node
                self.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)
                return node
            else:
                parent_node = self.right_children[0].get_node_at_index_with_tombstones(0)
                node = FugueTreeNode(self, FugueTree.get_next_node_id(), char, parent_node.node_id, 'left')
                self.__nodes[node.node_id] = node
                parent_node.add_left_child(node)
                return node
        
        parent_node = self.__get_node_at_index_without_tombstones(position - 1)
        node = parent_node.insert_char_at_next_index(FugueTree.get_next_node_id(), char)
        self.__nodes[node.node_id] = node
        return node

    def delete_char(self, position: int) -> FugueTreeNode:
        node = self.__get_node_at_index_without_tombstones(position)
        if not node.deleted:
            node.mark_deleted()
        return node

    def insert_char_at_node(self, parent_node_id: int, node_id: int, char: UniqueChar, direction: Literal['left','right']) -> None:
        if parent_node_id == 0: #Id is the root
            assert direction=='right'
            node = FugueTreeNode(self, node_id, char, parent_node_id, direction)
            self.__add_right_child(node)
        else:
            #Find parent node
            parent_node = self.__get_node_with_id(parent_node_id)
            #Add node to direction, preserve order of ids in the list.
            node = FugueTreeNode(self, node_id, char, parent_node_id, direction)
            if direction == 'left':
                parent_node.add_left_child(node)
            else:
                parent_node.add_right_child(node)
        self.__nodes[node.node_id] = node

    def __add_right_child(self, node: FugueTreeNode) -> None:
        #Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.right_children) and self.right_children[current_index].value.id < node.value.id:
            current_index += 1
        
        self.right_children.insert(current_index, node)

        #Update count
        self.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)

    def delete_node_with_id(self, id: int) -> None:
        #Find node with value
        node = self.__get_node_with_id(id)
        if not node.deleted:
            node.mark_deleted()
        #Mark node as deleted.

    #Only to be used when copying
    def set_node(self, node_id: int, node: FugueTreeNode) -> None:
        self.__nodes[node_id] = node

    def copy(self) -> FugueTree:
        tree_copy = FugueTree()
        tree_copy.__node_counter = self.__node_counter
        tree_copy.right_children = [node.copy(tree_copy) for node in self.right_children]
        tree_copy.count = self.count

        return tree_copy



class FugueTreeNode:

    node_id: int
    direction: Literal['left','right']
    parent_node_id: int

    tree: FugueTree

    value: UniqueChar
    left_children: list[FugueTreeNode]
    right_children: list[FugueTreeNode]
    deleted: bool
    count: int #Number of nodes (not including tombstone) in the subtree with this node as the root
    tombstone_count: int #Number of tombstones in this subtree

    def __init__(self, tree: FugueTree, node_id: int, value: UniqueChar, parent_node_id: int, direction: Literal['left','right']):
        self.node_id = node_id
        self.tree = tree
        self.value = value
        self.parent_node_id = parent_node_id
        self.direction = direction
        self.left_children = []
        self.right_children = []
        self.deleted = False
        self.count = 1
        self.tombstone_count = 0

    def traverse(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        for node in self.left_children:
            result += node.traverse()

        if not self.deleted:
            result.append(self.value)
        
        for node in self.right_children:
            result += node.traverse()

        return result
    
    def traverse_with_tombstones(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        for node in self.left_children:
            result += node.traverse_with_tombstones()

        result.append(self.value)
        
        for node in self.right_children:
            result += node.traverse_with_tombstones()

        return result

    def get_node_at_index_without_tombstones(self, index: int) -> FugueTreeNode:
        if index < 0 or index >= self.count:
            raise IndexError()
        
        current_count = 0

        for node in self.left_children:  
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count

        #Only include value at this node if it is not a tombstone
        if not self.deleted:
            current_count += 1
            if current_count == index + 1:
                return self
        
        for node in self.right_children:  
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count
        
        raise IndexError()
    
    def get_node_at_index_with_tombstones(self, index: int) -> FugueTreeNode:
        if index < 0 or index >= self.count + self.tombstone_count:
            raise IndexError()
        
        current_count = 0

        for node in self.left_children:  
            if current_count + node.count + node.tombstone_count >= index + 1:
                return node.get_node_at_index_with_tombstones(index - current_count)
            current_count += node.count + node.tombstone_count

        #Only include value at this node if it is not a tombstone
        current_count += 1
        if current_count == index + 1:
            return self
        
        for node in self.right_children:  
            if current_count + node.count + node.tombstone_count >= index + 1:
                return node.get_node_at_index_with_tombstones(index - current_count)
            current_count += node.count + node.tombstone_count
        
        raise IndexError()
    
    def insert_char_at_next_index(self, node_id: int, char: UniqueChar) -> FugueTreeNode:
        if len(self.right_children) == 0:
            node = FugueTreeNode(self.tree, node_id, char, self.node_id, 'right')
            self.right_children.append(node)
            self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)
        else:
            next_node = self.right_children[0].get_node_at_index_with_tombstones(0)
            node = FugueTreeNode(self.tree, node_id, char, next_node.node_id, 'left')
            next_node.add_left_child(node)
        return node
    
    def add_left_child(self, node: FugueTreeNode) -> None:
        #Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.left_children) and self.left_children[current_index].value.id < node.value.id:
            current_index += 1
        
        self.left_children.insert(current_index, node)

        #Update count
        self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)

    def add_right_child(self, node: FugueTreeNode) -> None:
        #Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.right_children) and self.right_children[current_index].value.id < node.value.id:
            current_index += 1
        
        self.right_children.insert(current_index, node)

        #Update count
        self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)


    def mark_deleted(self) -> None:
        if not self.deleted:
            self.deleted = True
            self.tree.add_to_counts_of_node_with_id(self.node_id, -1, 1)

    #Copy, changing what the tree is.
    def copy(self, tree: FugueTree) -> FugueTreeNode:
        node_copy = FugueTreeNode(tree, self.node_id, self.value, self.parent_node_id, self.direction)

        node_copy.left_children = [node.copy(tree) for node in self.left_children]
        node_copy.right_children = [node.copy(tree) for node in self.right_children]

        node_copy.deleted = self.deleted
        node_copy.tombstone_count = self.tombstone_count
        node_copy.count = self.count

        tree.set_node(self.node_id, node_copy)

        return node_copy

        

