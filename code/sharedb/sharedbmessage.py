from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from unique_char.uniquechar import UniqueChar


@dataclass
class ShareDBSkip:
    count: int


@dataclass
class ShareDBInsert:
    characters: list[UniqueChar]


@dataclass
class ShareDBDelete:
    count: int


# An operation is a list of components that iterate over the document: skip so many
# characters, insert these characters here, delete so many characters from here. The
# components of the type this is ported from are a number, a string and a count of
# characters to remove; a document here is a list of unique characters rather than a
# string, so an insert carries characters.
ShareDBComponent = ShareDBSkip | ShareDBInsert | ShareDBDelete
ShareDBOperation = list[ShareDBComponent]


# An operation a client has made but the server has not committed yet. The sequence number
# is handed out when the operation is sent, and the pair (client, sequence) is what lets
# the client recognise the commit of its own operation coming back.
@dataclass
class ShareDBSubmission:
    operation: ShareDBOperation
    sequence: int | None
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]


@dataclass
class ShareDBMessage:
    client_id: int
    sequence: int
    version: int  # The version of the document the operation applies to.
    operation: ShareDBOperation
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]
