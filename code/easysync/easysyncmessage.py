from dataclasses import dataclass

from easysync.easysyncchangeset import EasySyncChangeset


@dataclass
class EasySyncSubmission:
    client_id: int
    base_rev: int
    changeset: EasySyncChangeset


@dataclass
class EasySyncMessage:
    client_id: int
    new_rev: int
    changeset: EasySyncChangeset
