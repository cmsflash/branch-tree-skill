#!/usr/bin/env python3
"""Print the branch/worktree tree: who descends from whom, and by how much.

Parent inference: a branch's parent is the branch it shares the most history
with, among branches strictly closer to the trunk. Restricting candidates to
"closer to trunk" is what makes the result a tree rather than a cycle — two
branches can never claim each other.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field


def git(*args: str, cwd: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def count(rev_range: str, cwd: str | None) -> int:
    out = git("rev-list", "--count", rev_range, cwd=cwd)
    return int(out) if out.isdigit() else 0


def shared_patches(upstream: str, branch: str, cwd: str | None) -> int:
    """Commits on `branch` whose patch already exists on `upstream`.

    Uses patch-ids, not SHAs, so a rebase does not hide the relationship. This
    is the signal that identifies the real parent: after a parent is rebased,
    merge-base can collapse to the trunk for both candidates, and only patch
    equivalence still shows which branch the work actually came from.
    """
    out = git("cherry", upstream, branch, cwd=cwd)
    return sum(1 for line in out.splitlines() if line.startswith("-"))


@dataclass
class Branch:
    name: str
    worktree: str | None = None
    parent: str | None = None
    ahead: int = 0
    behind: int = 0
    children: list[str] = field(default_factory=list)


def worktree_map(cwd: str | None) -> dict[str, str]:
    """branch name -> worktree directory basename."""
    mapping: dict[str, str] = {}
    path: str | None = None
    for line in git("worktree", "list", "--porcelain", cwd=cwd).splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree ") :]
        elif line.startswith("branch ") and path:
            mapping[line[len("branch refs/heads/") :]] = path.rsplit("/", 1)[-1]
    return mapping


def detect_trunk(cwd: str | None) -> str:
    head = git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", cwd=cwd)
    if head.startswith("origin/"):
        return head[len("origin/") :]
    for candidate in ("main", "master", "trunk"):
        if git("rev-parse", "--verify", "--quiet", candidate, cwd=cwd):
            return candidate
    sys.exit("Could not determine the trunk branch; pass --trunk.")


def build(
    branch_names: list[str], trunk: str, cwd: str | None
) -> dict[str, Branch]:
    trees = worktree_map(cwd)
    branches = {n: Branch(name=n, worktree=trees.get(n)) for n in branch_names}
    branches.setdefault(trunk, Branch(name=trunk, worktree=trees.get(trunk)))

    # Distance from trunk orders the search: a parent is always strictly closer.
    distance = {n: count(f"{trunk}..{n}", cwd) for n in branches}

    for name in branch_names:
        if name == trunk:
            continue
        best: tuple[int, int, int, str] | None = None
        for cand in branches:
            if cand == name or distance[cand] >= distance[name]:
                continue
            base = git("merge-base", cand, name, cwd=cwd)
            if not base:
                continue
            # Rank by shared patches first (survives a rebase of either
            # side), then by fewest commits since the shared point, then by
            # the candidate nearest the trunk. Negated so "more" sorts first.
            #
            # Only a MAJORITY overlap counts. A branch sharing one incidental
            # commit is not a parent, and counting raw overlap lets such a
            # branch outrank the trunk even when it is hundreds of commits
            # further away.
            gap = count(f"{base}..{name}", cwd)
            shared = shared_patches(cand, name, cwd)
            ahead = count(f"{cand}..{name}", cwd)
            dominant = shared if ahead and shared * 2 > ahead else 0
            key = (-dominant, gap, distance[cand], cand)
            if best is None or key < best:
                best = key
        parent = best[3] if best else trunk
        branches[name].parent = parent
        branches[name].ahead = count(f"{parent}..{name}", cwd)
        branches[name].behind = count(f"{name}..{parent}", cwd)

    for name, br in branches.items():
        if br.parent and br.parent in branches:
            branches[br.parent].children.append(name)
    for br in branches.values():
        br.children.sort()
    return branches


def prune(
    branches: dict[str, Branch], trunk: str, keep: set[str]
) -> dict[str, Branch]:
    """Keep matched branches plus every ancestor needed to reach the trunk.

    Ancestors are retained rather than reparenting matched branches onto the
    trunk, so each branch keeps the parent its +A/-B was measured against.
    """
    needed: set[str] = {trunk}
    for name in keep:
        cursor: str | None = name
        while cursor and cursor in branches:
            needed.add(cursor)
            cursor = branches[cursor].parent
    kept = {n: b for n, b in branches.items() if n in needed}
    for br in kept.values():
        br.children = [c for c in br.children if c in kept]
    return kept


def render(branches: dict[str, Branch], trunk: str) -> list[str]:
    lines = [trunk]

    def emit(name: str, prefix: str) -> None:
        for child in branches[name].children:
            br = branches[child]
            label = f"{child}, {br.worktree}" if br.worktree else child
            lines.append(f"{prefix}│")
            lines.append(f"{prefix}└── {label} (+{br.ahead}/-{br.behind})")
            emit(child, prefix + "│   ")

    emit(trunk, "")
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("filter", nargs="?", help="regex; only branches matching are shown")
    ap.add_argument("--trunk", help="trunk branch (default: origin/HEAD, else main)")
    ap.add_argument("-C", dest="cwd", help="run in this repository")
    args = ap.parse_args()

    if not git("rev-parse", "--git-dir", cwd=args.cwd):
        return print("Not a git repository.", file=sys.stderr) or 1

    trunk = args.trunk or detect_trunk(args.cwd)
    names = git("for-each-ref", "--format=%(refname:short)", "refs/heads/", cwd=args.cwd).splitlines()
    if not names:
        print("No branches found.", file=sys.stderr)
        return 1

    keep: set[str] | None = None
    if args.filter:
        pattern = re.compile(args.filter)
        matched = {n for n in names if pattern.search(n)}
        if not matched:
            print(f"No branches match /{args.filter}/.", file=sys.stderr)
            return 1
        keep = matched

    # Parents are always inferred over EVERY branch, then the tree is pruned.
    # Inferring over the filtered set instead would let a filter change who
    # counts as a parent, silently changing the +A/-B a branch reports.
    branches = build(names, trunk, args.cwd)
    if keep is not None:
        branches = prune(branches, trunk, keep)
    print("\n".join(render(branches, trunk)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
