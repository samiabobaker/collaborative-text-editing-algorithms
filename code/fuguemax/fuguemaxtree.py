from typing import Literal, assert_never

from unique_char.uniquechar import UniqueChar

RightOriginId = int | Literal["end"] | None


class FugueMaxTree:
    __node_counter: int = 1

    @staticmethod
    def get_next_node_id() -> int:
        id = FugueMaxTree.__node_counter
        FugueMaxTree.__node_counter += 1
        return id

    node_id: int

    # left_children: list[FugueTreeNode] - The root will never have left children.
    right_children: list[FugueMaxTreeNode]

    __nodes: dict[int, FugueMaxTreeNode]

    count: int  # Not including tombstones

    def __init__(self):
        self.right_children = []
        self.node_id = 0
        self.count = 0
        self.__nodes = {}

    def __get_node_at_index_without_tombstones(self, index: int) -> FugueMaxTreeNode:
        if index < 0 or index >= self.count:
            raise IndexError()

        current_count = 0

        # for node in self.left_children:
        #    if current_count + node.count >= index:
        #        return node.get_node_at_index_without_tombstones(index - current_count)
        #    current_count += node.count

        for node in self.right_children:
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count

        raise IndexError()

    def __get_node_with_id(self, id: int) -> FugueMaxTreeNode:
        return self.__nodes[id]

    def get_node_with_id(self, id: int) -> FugueMaxTreeNode:
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
        # for node in self.left_children:
        #    result += node.traverse()

        for node in self.right_children:
            result += node.traverse()

        return result

    def traverse_with_right_origins(self) -> list[tuple[UniqueChar, UniqueChar | Literal["end"]]]:
        result: list[tuple[UniqueChar, UniqueChar | Literal["end"]]] = []

        for node in self.right_children:
            result += node.traverse_with_right_origins()

        return result

    def traverse_with_tombstones(self) -> list[UniqueChar]:
        result: list[UniqueChar] = []
        # for node in self.left_children:
        #    result += node.traverse()

        for node in self.right_children:
            result += node.traverse_with_tombstones()

        return result

    def insert_char(self, position: int, char: UniqueChar) -> FugueMaxTreeNode:
        if position < 0 or position > self.count:
            raise IndexError()

        if position == 0:
            if len(self.right_children) == 0:
                node = FugueMaxTreeNode(self, FugueMaxTree.get_next_node_id(), char, self.node_id, "right", "end")
                self.right_children.append(node)
                self.__nodes[node.node_id] = node
                self.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)
                return node
            else:
                parent_node = self.right_children[0].get_node_at_index_with_tombstones(0)
                node = FugueMaxTreeNode(self, FugueMaxTree.get_next_node_id(), char, parent_node.node_id, "left", None)
                self.__nodes[node.node_id] = node
                parent_node.add_left_child(node)
                return node

        parent_node = self.__get_node_at_index_without_tombstones(position - 1)
        node = parent_node.insert_char_at_next_index(FugueMaxTree.get_next_node_id(), char)
        self.__nodes[node.node_id] = node
        return node

    def delete_char(self, position: int) -> FugueMaxTreeNode:
        node = self.__get_node_at_index_without_tombstones(position)
        if not node.deleted:
            node.mark_deleted()
        return node

    def insert_char_at_node(
        self,
        parent_node_id: int,
        node_id: int,
        char: UniqueChar,
        direction: Literal["left", "right"],
        right_origin_id: int | Literal["end"] | None,
    ) -> None:
        if parent_node_id == 0:  # Id is the root
            assert direction == "right"
            node = FugueMaxTreeNode(self, node_id, char, parent_node_id, direction, right_origin_id)
            self.__add_right_child(node)
        else:
            # Find parent node
            parent_node = self.__get_node_with_id(parent_node_id)
            # Add node to direction, preserve order of ids in the list.
            node = FugueMaxTreeNode(self, node_id, char, parent_node_id, direction, right_origin_id)
            if direction == "left":
                parent_node.add_left_child(node)
            else:
                parent_node.add_right_child(node)
        self.__nodes[node.node_id] = node

    def __add_right_child(self, node: FugueMaxTreeNode) -> None:
        # Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.right_children) and self.compare_right_origins(
            self.right_children[current_index].right_origin_id,
            node.right_origin_id,
            self.right_children[current_index].node_id,
            node.node_id,
        ):
            # print(f"Comparing right origins of {self.right_children[current_index].value} and {node.value}")
            current_index += 1

        self.right_children.insert(current_index, node)

        # Update count
        self.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)

    # Returns true if id1 should appear before id2 in the right_children list (i.e, reverse id order, breaking ties of node id)
    def compare_right_origins(
        self, right_id1: RightOriginId, right_id2: RightOriginId, node_id1: int, node_id2: int
    ) -> bool:

        state = self.traverse()

        match right_id1, right_id2:
            case None, _:
                raise ValueError("Right origin id of right child should not be none.")
            case _, None:
                raise ValueError("Right origin id of right child should not be none.")
            case "end", "end":
                return node_id1 < node_id2
            case "end", _:
                return True
            case _, "end":
                return False
            case n1, n2:
                state = self.traverse_with_tombstones()

                node1 = self.__get_node_with_id(n1)
                node2 = self.__get_node_with_id(n2)

                index1 = state.index(node1.value)
                index2 = state.index(node2.value)

                return (index1 > index2) or (index1 == index2 and node_id1 < node_id2)
            case _ as unreachable:
                assert_never(unreachable)

    def delete_node_with_id(self, id: int) -> None:
        # Find node with value
        node = self.__get_node_with_id(id)
        if not node.deleted:
            node.mark_deleted()
        # Mark node as deleted.

    def get_right_origin_id_of_node_with_id(self, id: int) -> RightOriginId:
        node = self.__nodes[id]

        # If there is a right child, go down there.
        # if len(node.right_children) != 0:
        #    return node.get_node_at_index_with_tombstones(0).node_id

        if node.direction == "left":
            parent_node = self.__get_node_with_id(node.parent_node_id)

            index = parent_node.left_children.index(node)

            # Go to the next left child.
            if index < len(parent_node.left_children) - 1:
                return parent_node.left_children[index + 1].get_node_at_index_with_tombstones(0).node_id

            # If there are no more left children, then the next node is the parent node.
            return parent_node.node_id
        else:
            if node.parent_node_id == 0:  # If parent is the root
                index = self.right_children.index(node)

                if index < len(self.right_children) - 1:
                    return self.right_children[index + 1].get_node_at_index_with_tombstones(0).node_id
                else:
                    return "end"

            parent_node = self.__get_node_with_id(node.parent_node_id)

            index = parent_node.right_children.index(node)

            # Go to the next right child.
            if index < len(parent_node.right_children) - 1:
                return parent_node.right_children[index + 1].get_node_at_index_with_tombstones(0).node_id

            # If there are no more right children, recursively go up.
            return self.get_right_origin_id_of_node_with_id(parent_node.node_id)

        # Only to be used when copying

    def set_node(self, node_id: int, node: FugueMaxTreeNode) -> None:
        self.__nodes[node_id] = node

    def copy(self) -> FugueMaxTree:
        tree_copy = FugueMaxTree()
        tree_copy.__node_counter = self.__node_counter
        tree_copy.right_children = [node.copy(tree_copy) for node in self.right_children]
        tree_copy.count = self.count

        return tree_copy


class FugueMaxTreeNode:
    node_id: int
    direction: Literal["left", "right"]
    parent_node_id: int

    tree: FugueMaxTree

    value: UniqueChar
    left_children: list[FugueMaxTreeNode]
    right_children: list[FugueMaxTreeNode]
    deleted: bool
    count: int  # Number of nodes (not including tombstone) in the subtree with this node as the root
    tombstone_count: int  # Number of tombstones in this subtree

    right_origin_id: RightOriginId  # Right origin id is stored for right children

    def __init__(
        self,
        tree: FugueMaxTree,
        node_id: int,
        value: UniqueChar,
        parent_node_id: int,
        direction: Literal["left", "right"],
        right_origin_id: RightOriginId,
    ):
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
        self.right_origin_id = right_origin_id

        if direction == "right" and right_origin_id is None:
            raise ValueError("Every right child must have a right origin")

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

    def get_node_at_index_without_tombstones(self, index: int) -> FugueMaxTreeNode:
        if index < 0 or index >= self.count:
            raise IndexError()

        current_count = 0

        for node in self.left_children:
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count

        # Only include value at this node if it is not a tombstone
        if not self.deleted:
            current_count += 1
            if current_count == index + 1:
                return self

        for node in self.right_children:
            if current_count + node.count >= index + 1:
                return node.get_node_at_index_without_tombstones(index - current_count)
            current_count += node.count

        raise IndexError()

    def get_node_at_index_with_tombstones(self, index: int) -> FugueMaxTreeNode:
        if index < 0 or index >= self.count + self.tombstone_count:
            raise IndexError()

        current_count = 0

        for node in self.left_children:
            if current_count + node.count + node.tombstone_count >= index + 1:
                return node.get_node_at_index_with_tombstones(index - current_count)
            current_count += node.count + node.tombstone_count

        # Only include value at this node if it is not a tombstone
        current_count += 1
        if current_count == index + 1:
            return self

        for node in self.right_children:
            if current_count + node.count + node.tombstone_count >= index + 1:
                return node.get_node_at_index_with_tombstones(index - current_count)
            current_count += node.count + node.tombstone_count

        raise IndexError()

    def insert_char_at_next_index(self, node_id: int, char: UniqueChar) -> FugueMaxTreeNode:
        if len(self.right_children) == 0:
            right_origin_id = self.tree.get_right_origin_id_of_node_with_id(self.node_id)
            node = FugueMaxTreeNode(self.tree, node_id, char, self.node_id, "right", right_origin_id)
            self.right_children.append(node)
            self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)
        else:
            next_node = self.right_children[0].get_node_at_index_with_tombstones(0)
            node = FugueMaxTreeNode(self.tree, node_id, char, next_node.node_id, "left", None)
            next_node.add_left_child(node)
        return node

    def add_left_child(self, node: FugueMaxTreeNode) -> None:
        # Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.left_children) and self.left_children[current_index].value.id < node.value.id:
            current_index += 1

        self.left_children.insert(current_index, node)

        # Update count
        self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)

    def add_right_child(self, node: FugueMaxTreeNode) -> None:
        # Adds child to left_children while preserving order of ids.
        current_index = 0
        while current_index < len(self.right_children) and self.tree.compare_right_origins(
            self.right_children[current_index].right_origin_id,
            node.right_origin_id,
            self.right_children[current_index].node_id,
            node.node_id,
        ):
            # print(f"Comparing right origins of {self.right_children[current_index].value} and {node.value}")
            current_index += 1

        self.right_children.insert(current_index, node)

        # Update count
        self.tree.add_to_counts_of_node_with_id(self.node_id, node.count, node.tombstone_count)

    def mark_deleted(self) -> None:
        if not self.deleted:
            self.deleted = True
            self.tree.add_to_counts_of_node_with_id(self.node_id, -1, 1)

    def traverse_with_right_origins(self) -> list[tuple[UniqueChar, UniqueChar | Literal["end"]]]:
        result: list[tuple[UniqueChar, UniqueChar | Literal["end"]]] = []

        for node in self.left_children:
            result += node.traverse_with_right_origins()

        if not self.deleted and self.right_origin_id is not None:
            result.append(
                (
                    self.value,
                    "end" if self.right_origin_id == "end" else self.tree.get_node_with_id(self.right_origin_id).value,
                )
            )

        for node in self.right_children:
            result += node.traverse_with_right_origins()

        return result

    # Copy, changing what the tree is.
    def copy(self, tree: FugueMaxTree) -> FugueMaxTreeNode:
        node_copy = FugueMaxTreeNode(
            tree, self.node_id, self.value, self.parent_node_id, self.direction, self.right_origin_id
        )

        node_copy.left_children = [node.copy(tree) for node in self.left_children]
        node_copy.right_children = [node.copy(tree) for node in self.right_children]

        node_copy.deleted = self.deleted
        node_copy.tombstone_count = self.tombstone_count
        node_copy.count = self.count

        tree.set_node(self.node_id, node_copy)

        return node_copy
