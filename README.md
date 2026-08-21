# branch-tree

An agent skill that reports git branches and worktrees as an ancestry tree:

```text
main
│
└── feat/gcs-explorer, gcs-explorer (+15/-0)
│   │
│   └── feat/gcs-explorer-sort-filter, gcs-explorer-sortfilter (+19/-59)
│
└── feat/other (+2/-1)
```

Indentation is descent, `, name` is the worktree the branch is checked out in
(omitted when there is none), and `(+A/-B)` counts commits ahead of and behind
the **parent** — not the trunk, which is what makes a stale stack obvious.

## Usage

```bash
python3 scripts/branch_tree.py                     # every local branch
python3 scripts/branch_tree.py gcs                 # branches matching /gcs/
python3 scripts/branch_tree.py -C ~/Programs/core  # another repo
python3 scripts/branch_tree.py --trunk develop     # non-standard trunk
```

No dependencies beyond Python 3.10+ and `git`.

## Why it uses patch-ids

Parents are inferred from patch-equivalent commits (`git cherry`) rather than
merge-base distance. When a parent branch is rebased, its merge-base with its
own child collapses to the trunk, and distance-based inference reports the child
as a sibling of its parent. Patch-ids survive rebases, so the real relationship
still shows. See `SKILL.md` for the worked example.

## Install

Symlinked into the central skill store:

```bash
ln -s ~/Programs/skills/branch-tree ~/.agents/skills/branch-tree
ln -s ~/.agents/skills/branch-tree ~/.claude/skills/branch-tree
```
