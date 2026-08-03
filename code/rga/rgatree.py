from unique_char.uniquechar import UniqueChar
from dataclasses import dataclass

@dataclass(frozen=True, order=True)
class RGATimestamp:
    """Timestamp of one insertion, and thereby the identity of one node.

    The paper's set C of timestamps: pairs (x, i) of a counter and a replica
    identifier, ordered lexicographically. Comparing the counter first makes a
    timestamp a Lamport clock - a node is always younger than everything its
    author had already seen - and the client id is only ever consulted to break
    a tie between two replicas that inserted with the same counter.
    """

    counter: int
    client_id: int

    def less_than(self, other : RGATimestamp) -> bool:
        return (self.counter < other.counter) or ((self.counter == other.counter) and self.client_id < other.client_id)


class RGANode:
    """One element of the list, held as a node of the insertion tree.

    This is the paper's node (a, t, p): the element, the timestamp of its
    insertion, and the timestamp of the node it was inserted directly after.
    A parent of None is the root symbol, meaning "inserted at the very start of
    the document".

    The paper keeps deletions in a separate set T of deleted elements and never
    touches the tree. Elements here are UniqueChars, so elements and timestamps
    are in bijection and a flag on the node carries exactly the same
    information; `deleted` is that set, stored node by node.
    """

    value: UniqueChar
    timestamp: RGATimestamp
    parent: RGATimestamp | None
    children: list[RGANode]  # kept in decreasing timestamp order
    deleted: bool

    def __init__(
        self,
        value: UniqueChar,
        timestamp: RGATimestamp,
        parent: RGATimestamp | None,
    ):
        self.value = value
        self.timestamp = timestamp
        self.parent = parent
        self.children = []
        self.deleted = False

    def traverse(self) -> list[RGANode]:
        state : list[RGANode] = []

        if not self.deleted:
            state.append(self)

        for child in self.children:
            state += child.traverse()

        return state

    def add_child(self, node : RGANode) -> None:
        index = 0 
        while index < len(self.children) and node.timestamp.less_than(self.children[index].timestamp):
            index += 1
        self.children.insert(index, node)

    def mark_deleted(self) -> None:
        self.deleted = True

class RGATree:
    client_id: int
    children: list[RGANode]  # kept in decreasing timestamp order
    max_counter : int
    nodes : dict[tuple[int, int], RGANode] # (counter, client_id) => node

    def __init__(
        self,
        client_id : int
    ):
        self.children = []
        self.max_counter = 0
        self.client_id = client_id
        self.nodes = {}

    def traverse(self) -> list[RGANode]:
        state : list[RGANode] = []

        for child in self.children:
            state += child.traverse()

        return state

    def find_node_at_position(self, position: int) -> RGANode:
        state = self.traverse()
        return state[position]

    def insert_char(self, char: UniqueChar, position: int) -> RGANode:
        self.max_counter += 1
        new_timestamp = RGATimestamp(self.max_counter, self.client_id)

        if position == 0:
            node = RGANode(char, new_timestamp, None)
            self.children.insert(0, node)
        else:
            previous = self.find_node_at_position(position - 1)
            node = RGANode(char, new_timestamp, previous.timestamp)
            previous.add_child(node)
        self.nodes[(new_timestamp.client_id, new_timestamp.counter)] = node
        return node

    def delete_char_at_position(self, position : int) -> RGANode:
        node = self.find_node_at_position(position)
        node.mark_deleted()
        return node

    def delete_node_with_timestamp(self, timestamp : RGATimestamp):
        node = self.nodes[(timestamp.client_id, timestamp.counter)]
        node.mark_deleted()

    def add_child(self, node : RGANode) -> None:
            index = 0 
            while index < len(self.children) and node.timestamp.less_than(self.children[index].timestamp):
                index += 1
            self.children.insert(index, node)

    def insert_node(self, timestamp : RGATimestamp, parent : RGATimestamp | None, char : UniqueChar):
        node = RGANode(char, timestamp, parent)
        self.nodes[(timestamp.client_id, timestamp.counter)]  = node
        if parent == None:
            self.add_child(node)
        else:
            parent_node = self.nodes[(parent.client_id, parent.counter)]
            parent_node.add_child(node)
        self.max_counter = max(self.max_counter, timestamp.counter)