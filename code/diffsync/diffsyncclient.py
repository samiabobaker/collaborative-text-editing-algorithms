from typing import assert_never

from device.clientdevice import ClientDevice
from device.operations import (
    ClientDeleteOperation,
    ClientInsertOperation,
    ClientOperation,
    ClientReceiveFromClientOperation,
    ClientReceiveFromServerOperation,
    ClientTimestepOperation,
)
from diffsync.diffsyncmessage import DiffsyncMessage
from diffsync.diffsyncminigit import DiffsyncCommit, DiffsyncMiniGit
from unique_char.uniquechar import UniqueChar


class DiffsyncClient(ClientDevice):
    """A peer holding a commit graph and the text its heads merge to.

    The algorithm works over strings, so each character is encoded as the
    character whose code point is its identifier. The diff is then sensitive to
    exactly the distinctions the checkers care about, since two encoded texts
    are equal precisely when they are the same sequence of characters.

    Every local edit broadcasts a snapshot of the whole commit graph, and a
    receive folds the next queued snapshot in. Commits are immutable and
    merging one already held changes nothing, so a snapshot arriving stale is
    harmless.
    """

    client_id: int

    minigit: DiffsyncMiniGit
    text: list[UniqueChar]
    char_map: dict[int, UniqueChar]
    clients: list[DiffsyncClient]
    message_buffer: dict[int, list[DiffsyncMessage]]

    def __init__(self, client_id: int):
        self.client_id = client_id
        self.minigit = DiffsyncMiniGit()
        self.text = []
        self.char_map = {}
        self.clients = []
        self.message_buffer = {}

    def set_clients(self, clients: list[DiffsyncClient]) -> None:
        self.clients = clients
        for client in clients:
            self.message_buffer[client.client_id] = []

    def __text_to_str(self) -> str:
        return "".join(chr(character.id) for character in self.text)

    def __str_to_text(self, s: str) -> list[UniqueChar]:
        return [self.char_map[ord(character)] for character in s]

    def perform_operation(self, operation: ClientOperation) -> list[ClientInsertOperation | ClientDeleteOperation]:
        match operation:
            case ClientInsertOperation():
                return self.perform_local_insert(operation)
            case ClientDeleteOperation():
                return self.perform_local_delete(operation)
            case ClientReceiveFromServerOperation():
                return []
            case ClientReceiveFromClientOperation(_, sender_client_id):
                return self.receive_from_client(sender_client_id)
            case ClientTimestepOperation():
                return []
            case _ as unreachable:
                assert_never(unreachable)

    def perform_local_insert(
        self, operation: ClientInsertOperation
    ) -> list[ClientInsertOperation | ClientDeleteOperation]:
        self.text.insert(operation.position, operation.character)
        self.char_map[operation.character.id] = operation.character
        self.minigit.commit(self.__text_to_str(), self.client_id, op=operation)
        self.__broadcast()
        return [operation]

    def perform_local_delete(
        self, operation: ClientDeleteOperation
    ) -> list[ClientInsertOperation | ClientDeleteOperation]:
        self.text.pop(operation.position)
        self.minigit.commit(self.__text_to_str(), self.client_id, op=operation)
        self.__broadcast()
        return [operation]

    def __broadcast(self) -> None:
        for client in self.clients:
            if client.client_id == self.client_id:
                continue
            client.send_message(self.client_id, DiffsyncMessage(dict(self.minigit.commits), dict(self.char_map)))

    def send_message(self, client_id: int, message: DiffsyncMessage) -> None:
        self.message_buffer[client_id].append(message)

    def receive_from_client(self, sender_client_id: int) -> list[ClientInsertOperation | ClientDeleteOperation]:
        buffer = self.message_buffer[sender_client_id]
        if len(buffer) == 0:
            return []
        message = buffer.pop(0)

        new_commits: list[DiffsyncCommit] = []
        for cid, commit in message.commits.items():
            if cid not in self.minigit.commits:
                new_commits.append(commit)

        self.char_map.update(message.char_map)
        self.minigit.merge(message.commits)
        self.text = self.__str_to_text(self.minigit.cache)

        # The operations this receive made visible, in a fixed order. The id is
        # "{client_id}-{seq}", so it is ordered by those two numbers rather than
        # as a string, which would put a tenth commit before a second one.
        new_commits.sort(key=lambda commit: tuple(int(part) for part in commit.id.split("-")))
        return [commit.op for commit in new_commits if commit.op is not None]

    def read_state(self) -> list[UniqueChar]:
        return list(self.text)

    def can_receive_from_server(self) -> bool:
        return False

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client in self.clients:
            if len(self.message_buffer[client.client_id]) != 0:
                client_ids.append(client.client_id)
        return client_ids
