from __future__ import annotations

from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from sync7.sync7document import Sync7Id, Sync7Version


@dataclass
class Sync7Message:
    versions: dict[Sync7Id, Sync7Version]
    causing_operations: dict[Sync7Id, ClientInsertOperation | ClientDeleteOperation]
