from dataclasses import dataclass

from device.operations import ClientDeleteOperation, ClientInsertOperation
from diffsync.diffsyncmerge import Patch, apply_diff_patch, get_diff_patch_2, get_merged_diff_patch


@dataclass
class DiffsyncCommit:
    """One node of the commit graph, immutable once created.

    to_parents[p] is the patch taking this commit's text to p's text, and
    from_parents[p] the patch taking p's text to this commit's. A full text
    snapshot is stored only on a root commit, one with no parents.

    op is metadata this harness needs and the algorithm does not: the
    operation the commit was created by. The reference implementation works
    over plain text and carries no such field.
    """

    id: str
    to_parents: dict[str, Patch]
    from_parents: dict[str, Patch]
    text: str | None
    op: ClientInsertOperation | ClientDeleteOperation | None


class DiffsyncMiniGit:
    """A git-like graph of text commits whose heads are merged three-way.

    A local edit becomes a commit whose parents are all the current heads, so
    editing after a merge produces a merge commit exactly as git does. Peers
    synchronise by exchanging commits, and the document text is recomputed by
    recursively merging the heads.

    Commits are identified by a globally unique id. The reference
    implementation draws 15 random characters from a 62-symbol alphabet; this
    port uses "{client_id}-{seq}" so that seeding the harness replays a run
    bit-for-bit. Since ids are unique and commits immutable, a commit already
    known can be skipped on merge rather than having its fields extended.

    The reference implementation also prunes history, storing a fresh text
    snapshot when it drops a commit's ancestry. This port keeps the whole
    graph, so a snapshot only ever appears on a root commit.
    """

    def __init__(self) -> None:
        self.commits: dict[str, DiffsyncCommit] = {}
        # to_children[parent_id][child_id] is the patch taking the parent's
        # text to the child's.
        self.to_children: dict[str, dict[str, Patch]] = {}
        self.commit_cache: dict[str, str] = {}
        # The heads of the graph. The reference folds these in the order the
        # replica happened to learn them, so three replicas holding the same
        # commits can merge them differently; rec_merge sorts the ids first,
        # the one line fix proposed upstream, so every replica folds alike.
        self.leaves: dict[str, bool] = {}
        self.cache: str = ""
        self.__next_seq = 0

    def new_commit_id(self, client_id: int) -> str:
        self.__next_seq += 1
        return f"{client_id}-{self.__next_seq}"

    def commit(
        self,
        s: str,
        client_id: int,
        op: ClientInsertOperation | ClientDeleteOperation | None = None,
    ) -> None:
        """Record a local edit as a commit over all the current heads.

        The new text is s. A text that did not change makes no commit.
        """
        if s == self.cache:
            return

        commit_id = self.new_commit_id(client_id)
        to_parents: dict[str, Patch] = {}
        from_parents: dict[str, Patch] = {}
        text: str | None = None

        if len(self.leaves) == 0:
            # Nothing to descend from, so this is a root and stores its text.
            text = s
        else:
            for leaf in self.leaves:
                to_leaf, from_leaf = get_diff_patch_2(s, self.get_text(leaf))
                to_parents[leaf] = to_leaf
                from_parents[leaf] = from_leaf

        c = DiffsyncCommit(
            id=commit_id,
            to_parents=to_parents,
            from_parents=from_parents,
            text=text,
            op=op,
        )

        self.commits[c.id] = c
        self.calc_children()
        self.leaves = {c.id: True}
        self.commit_cache[c.id] = s
        self.cache = s
        self.purge_cache()

    def merge(self, commits: dict[str, DiffsyncCommit]) -> None:
        """Take a peer's commits into the graph and recompute the text.

        Merging never creates a commit, and merging the same commits twice changes
        nothing.
        """
        for cid, c in commits.items():
            if cid not in self.commits:
                self.commits[cid] = c

        self.calc_children()
        self.leaves = self.get_leaves()
        self.cache = self.rec_merge(self.leaves)
        self.purge_cache()

    def calc_children(self) -> None:
        self.to_children = {cid: {} for cid in self.commits}
        for cid, c in self.commits.items():
            for p_id, patch in c.from_parents.items():
                self.to_children[p_id][cid] = patch

    def purge_cache(self) -> None:
        """Drop the cached text of any commit that is neither a head nor a root.

        It can be recomputed from the patches.
        """
        for cid, c in self.commits.items():
            if len(c.to_parents) > 0 and cid not in self.leaves:
                self.commit_cache.pop(cid, None)

    def get_text(self, commit_id: str) -> str:
        """The full text of a commit.

        Search outwards until a commit whose text is known is reached, then walk back
        along that path applying each patch in turn.
        """
        if commit_id in self.commit_cache:
            return self.commit_cache[commit_id]

        frontier = [commit_id]
        back_pointers: dict[str, str] = {commit_id: commit_id}
        while True:
            if not frontier:
                raise ValueError("the commit graph is missing a commit it refers to")
            next_id = frontier.pop(0)

            c_id = next_id
            c = self.commits[c_id]
            text = c.text if c.text is not None else self.commit_cache.get(c_id)
            if text is not None:
                snowball = text
                while True:
                    if next_id == commit_id:
                        self.commit_cache[commit_id] = snowball
                        return snowball
                    next_id = back_pointers[next_id]
                    # The step from c_id to next_id runs either up to a parent
                    # or down to a child, and both patches are stored in the
                    # direction "c_id's text to next_id's text".
                    patch = self.commits[c_id].to_parents.get(next_id)
                    if patch is None:
                        patch = self.to_children[c_id].get(next_id)
                    assert patch is not None
                    snowball = apply_diff_patch(snowball, patch)
                    c_id = next_id
                    c = self.commits[c_id]

            for p_id in c.to_parents:
                if p_id not in back_pointers:
                    back_pointers[p_id] = next_id
                    frontier.append(p_id)
            for ch_id in self.to_children[c_id]:
                if ch_id not in back_pointers:
                    back_pointers[ch_id] = next_id
                    frontier.append(ch_id)

    def rec_merge(self, these: dict[str, bool]) -> str:
        """Merge the given commits' texts into one.

        The merged text starts as the first commit's. Each further commit is
        merged into it against a base, and that base is itself the recursive
        merge of the heads of the two sides' common ancestors, the same way git
        builds a virtual base when several candidates exist.

        The fold runs over the head ids in sorted order, the one line fix
        proposed upstream: the reference folds in the order the replica
        learned the commits, which lets replicas holding the same commits
        merge them differently.
        """
        ids = sorted(these)
        if len(ids) == 0:
            return ""
        r = self.get_text(ids[0])
        if len(ids) == 1:
            return r
        r_ancestors = self.get_ancestors(ids[0])
        for i in ids[1:]:
            i_ancestors = self.get_ancestors(i)
            # The ancestors the two sides share.
            common = {k: v for k, v in r_ancestors.items() if k in i_ancestors}
            o = self.rec_merge(self.get_leaves(common))
            r = apply_diff_patch(o, get_merged_diff_patch(r, self.get_text(i), o))
            r_ancestors.update(i_ancestors)
        return r

    def get_leaves(self, commits: dict[str, DiffsyncCommit] | None = None) -> dict[str, bool]:
        """The heads among the given commits, defaulting to all of them: those with no child."""
        if commits is None:
            commits = self.commits
        leaves = {cid: True for cid in commits}
        for cid in commits:
            for p_id in self.commits[cid].to_parents:
                leaves.pop(p_id, None)
        return leaves

    def get_ancestors(self, commit_id: str) -> dict[str, DiffsyncCommit]:
        """Every strict ancestor of a commit."""
        frontier = [commit_id]
        ancestors: dict[str, DiffsyncCommit] = {}
        while len(frontier) > 0:
            next_id = frontier.pop(0)
            for p_id in self.commits[next_id].to_parents:
                if p_id not in ancestors:
                    ancestors[p_id] = self.commits[p_id]
                    frontier.append(p_id)
        return ancestors
