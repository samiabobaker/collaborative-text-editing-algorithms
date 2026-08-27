from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


# An insertion names the element it goes after rather than an index, and that
# element may already be deleted. A before_id of None inserts at the start.
@dataclass
class TWCInsertionOperation:
    update_id: int
    before_id: int | None
    element_id: int
    character: UniqueChar


# A deletion names the element to mark deleted. The element keeps its place as a
# tombstone so that later insertions can still be placed after it.
@dataclass
class TWCDeletionOperation:
    update_id: int
    element_id: int


TWCOperation = TWCInsertionOperation | TWCDeletionOperation


# Sent by a client, before the server has given it a place in the total order.
@dataclass
class TWCMessage:
    operation: TWCOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation


# Broadcast by the server once it has a server_version, to every client including
# the sender. That echo is what moves the sender's own update out of pending.
@dataclass
class TWCCommittedMessage:
    server_version: int
    operation: TWCOperation
    causing_operation: ClientInsertOperation | ClientDeleteOperation
