from typing import TYPE_CHECKING, assert_never

from device.operations import ServerOperation, ServerReceiveFromClientOperation
from device.serverdevice import ServerDevice
from easysync.easysyncchangeset import EasySyncChangeset, apply_to_text, follow
from easysync.easysyncmessage import EasySyncMessage, EasySyncSubmission
from unique_char.uniquechar import UniqueChar

if TYPE_CHECKING:
    from easysync.easysyncclient import EasySyncClient


class EasySyncServer(ServerDevice):
    clients: dict[int, EasySyncClient]

    revisions: list[EasySyncChangeset]
    revision_authors: list[int]

    text: list[UniqueChar]
    client_revs: dict[int, int]

    message_buffers: dict[int, list[EasySyncSubmission]]

    def __init__(self, clients: list[EasySyncClient]):
        self.clients = {}
        self.revisions = []
        self.revision_authors = []
        self.text = []
        self.client_revs = {}
        self.message_buffers = {}

        for client in clients:
            self.clients[client.client_id] = client
            self.client_revs[client.client_id] = -1
            self.message_buffers[client.client_id] = []

    def __head_revision_number(self) -> int:
        return len(self.revisions) - 1

    def __append_revision(self, changeset: EasySyncChangeset, author_id: int) -> int:
        self.text = apply_to_text(self.text, changeset)
        self.revisions.append(changeset)
        self.revision_authors.append(author_id)
        return self.__head_revision_number()

    def send_message(self, client_id: int, message: EasySyncSubmission):
        self.message_buffers[client_id].append(message)

    def receive_message(self, client_id: int):
        if client_id not in self.message_buffers or len(self.message_buffers[client_id]) == 0:
            return

        submission = self.message_buffers[client_id].pop(0)

        rebased_changeset = submission.changeset
        for revision_number in range(submission.base_rev + 1, len(self.revisions)):
            rebased_changeset = follow(self.revisions[revision_number], rebased_changeset, False)

        new_rev = self.__append_revision(rebased_changeset, client_id)

        self.clients[client_id].send_message(EasySyncMessage(client_id, new_rev, rebased_changeset))
        self.client_revs[client_id] = new_rev

        self.__update_clients()

    def __update_clients(self):
        head = self.__head_revision_number()
        for client_id in self.clients:
            while self.client_revs[client_id] < head:
                revision_number = self.client_revs[client_id] + 1
                self.clients[client_id].send_message(
                    EasySyncMessage(
                        self.revision_authors[revision_number], revision_number, self.revisions[revision_number]
                    )
                )
                self.client_revs[client_id] = revision_number

    def perform_operation(self, operation: ServerOperation) -> None:
        match operation:
            case ServerReceiveFromClientOperation(client_id):
                self.receive_message(client_id)
            case _ as unreachable:
                assert_never(unreachable)

    def can_receive_from(self) -> list[int]:
        client_ids: list[int] = []
        for client_id in self.clients:
            if len(self.message_buffers[client_id]) != 0:
                client_ids.append(client_id)
        return client_ids
