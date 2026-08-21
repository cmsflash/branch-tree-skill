---
name: branch-tree
description: "Report git branches and worktrees as an ancestry tree, showing which branch descends from which and how far each has diverged (+ahead/-behind versus its parent, not the trunk). Use when asked what branches or worktrees exist, how they relate, which is stacked on which, what is safe to delete, or to summarize the state of a feature spanning several branches. Triggers: 'what branches do we have', 'branch structure', 'worktree structure', 'show the stack', 'how do these branches relate', 'which branches are related to this feature'."
---

# Branch tree: reporting branch and worktree structure

Report branch relationships in one fixed format so the shape of the work is
readable at a glance:

```text
main
│
└── feat/gcs-explorer, gcs-explorer (+15/-0)
│   │
│   └── feat/gcs-explorer-sort-filter, gcs-explorer-sortfilter (+19/-59)
│
└── feat/other (+2/-1)
```

Read it as:

- **Indentation is descent.** A nested branch was built on its parent, not on
  the trunk.
- **`, name` after the branch is the worktree directory** it is checked out in.
  Omit it entirely when the branch has no worktree.
- **`(+A/-B)` is measured against the PARENT, not the trunk.** `+15/-0` means 15
  commits the parent lacks and none of the parent's missing — a clean stack.
  A large `-B` means the branch is stale and needs a rebase.

## Generating it

```bash
python3 scripts/branch_tree.py                     # every local branch
python3 scripts/branch_tree.py gcs                 # only branches matching /gcs/
python3 scripts/branch_tree.py -C ~/Programs/core  # a different repo
python3 scripts/branch_tree.py --trunk develop     # non-standard trunk
```

The filter is a regex matched against branch names; the trunk is always kept so
the tree still has a root. Trunk is detected from `origin/HEAD`, falling back to
`main`, `master`, then `trunk`.

## Why parent inference needs patch-ids

The parent is the candidate branch sharing the most **patch-equivalent commits**
(`git cherry`), tie-broken by fewest commits since the merge-base, then by
proximity to the trunk. Only branches strictly closer to the trunk are eligible,
which is what guarantees a tree rather than a cycle.

Ranking on merge-base distance alone is the obvious approach and it is wrong.
Once a parent branch is rebased, its merge-base with its own child collapses to
the trunk — identical to the trunk's own merge-base — and the child gets
reported as a sibling of its parent. Patch-ids survive the rebase because the
content is unchanged even though every SHA differs. In a real case this was the
difference between:

```text
main
│
└── feat/gcs-explorer (+15/-0)
│
└── feat/gcs-explorer-sort-filter (+19/-44)     # WRONG: shown as a sibling
```

and the truth, where sort-filter carried 15 patches already on the explorer
branch:

```text
main
│
└── feat/gcs-explorer (+15/-0)
│   │
│   └── feat/gcs-explorer-sort-filter (+19/-59)
```

## Reading the numbers before acting

- **`+N/-0`** — a clean stack. Safe to merge in order.
- **large `-B`** — stale; rebase before review, or the diff includes unrelated
  drift.
- **high `+A` with a big `-B`** — usually duplicated pre-rebase commits, not new
  work. Check with `git cherry <parent> <branch> | grep -c '^-'`: those marked
  `-` already exist upstream and will vanish on rebase.

A merged branch may still show `+N`, because a squash-merge rewrites the commit.
Verify by content, not ancestry:

```bash
git diff origin/main <branch> --stat   # empty output = fully merged, safe to delete
```

`git merge-base --is-ancestor` reports "not merged" for squash-merged branches
and will talk you out of deleting something that is genuinely gone.

## Reporting to a human

Give the tree, then the decisions it implies — which branch is the PR, which is
stale, what is safe to delete. The tree is the evidence, not the answer. Do not
delete a branch or worktree on the strength of the numbers alone; confirm with
the diff check above.
