from dataclasses import dataclass

from diffsync.diffsyncminigit import DiffsyncCommit
from unique_char.uniquechar import UniqueChar


# There is no insertion or deletion operation to send here. diffsync does not
# ship edits at all: it ships commits, and the receiver works out what changed
# by diffing texts. A message carries a snapshot of the sender's whole commit
# graph, which is safe to send blind because commits are immutable and merging
# one already held is a no-op, and the character table needed to decode the
# texts travels with it.
@dataclass
class DiffsyncMessage:
    commits: dict[str, DiffsyncCommit]
    char_map: dict[int, UniqueChar]
