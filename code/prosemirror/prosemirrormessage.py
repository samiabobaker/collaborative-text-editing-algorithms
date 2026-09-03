from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from prosemirror.prosemirrortransform import ProseMirrorStep


@dataclass
class ProseMirrorMessage:
    client_id: int
    version: int
    steps: list[ProseMirrorStep]
    causing_operations: list[ClientInsertOperation | ClientDeleteOperation]
