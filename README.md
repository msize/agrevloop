# agrevloop

An Author writes an OpenSpec change, a Reviewer reviews every step, in one agwinterm split. Either
role can be Claude Code or Codex. Phase 1 is the proposal with spec deltas, phase 2 the tasks,
phase 3 the implementation task by task. Each step goes back and forth until the Reviewer
approves, at most three rounds. The human passes the gates and commits at the end.

Each harness gets the same pair of thin skills, `agrevloop-author` and `agrevloop-reviewer`. The
transport is agworkbench's vendored, fail-closed tooling: `agmsg` (a file mailbox), `peerchat`
(the doorbell that types one pointer line into a provably empty composer) and `wb.py wait-mail`
(Claude's background waiter).

| piece | what |
|---|---|
| `skills/claude/agrevloop-author` | Claude as Author: phases, rounds, gates, staging checkpoints |
| `skills/claude/agrevloop-reviewer` | Claude as Reviewer: reviews with `CLAUDE_REVIEW_SKILL`, answers by mail |
| `skills/codex/agrevloop-author` | Codex as Author, inside its sandbox |
| `skills/codex/agrevloop-reviewer` | Codex as Reviewer: reviews with `CODEX_REVIEW_SKILL`, answers by mail |
| `bin/agr.py` | one wrapper for all: mailbox at `<checkout>/.agrevloop/`, one box per role |
| `bin/agrevloop-claude` | registers the pane, starts Claude with the role's skill |
| `bin/agrevloop-codex` | registers the pane, starts Codex sandboxed with the mailbox in its tool environment |

## Requirements

- [yeroo/agwinterm](https://github.com/yeroo/agwinterm) with `agwintermctl` on PATH, Git Bash, Python 3.10+
- [yeroo/agworkbench](https://github.com/yeroo/agworkbench) cloned next to this repo, or `AGWORKBENCH` set
- Claude Code, Codex CLI, OpenSpec CLI, and a review skill for each harness that plays Reviewer
  (see How to review in the reviewer skills)

## Install

```bash
CODEX_REVIEW_SKILL='$<plugin>:<review-skill>' \
CLAUDE_REVIEW_SKILL='/<plugin>:<review-skill>' ./install.sh   # how each harness invokes its review skill
export PATH="<path-to-agrevloop>/bin:$PATH"                   # for agrevloop-claude and agrevloop-codex
```

## Use

1. In the project checkout, open an agwinterm split.
2. Right pane, the Reviewer: `agrevloop-codex reviewer` or `agrevloop-claude reviewer`. It waits
   for mail.
3. Left pane, the Author: `agrevloop-claude author add-retry-policy gates=p1` or
   `agrevloop-codex author add-retry-policy gates=p1`, or describe the change instead of naming it.
   Arguments after `--` go to `claude` or `codex` unchanged.

| Author | Reviewer | |
|---|---|---|
| Claude | Codex | yes |
| Codex | Claude | yes |
| Claude | Claude | yes |
| Codex | Codex | no: nobody could wake the other |

A Claude Author can also be started as plain `claude` with `/agrevloop-author ...`, a Claude
Reviewer with `/agrevloop-reviewer`: the skill runs `init` itself.

Each launcher runs `agr.py --as <role> init --tool <tool>`, which creates `.agrevloop/`, adds it
and `review-runs/` to `.git/info/exclude`, and registers its own pane under its role. From there
`agr.py send` picks the doorbell by the recipient: a Codex pane gets a `Chat from Claude:` pointer
typed into its composer, a Claude pane is woken by its own background waiter.

`.git/info/exclude` is the checkout's own ignore file: it works like `.gitignore` but is never
committed, so the project's `.gitignore` stays untouched and nobody else sees the entries.
`git check-ignore -v .agrevloop/` shows the rule.

## How it is bounded

- Codex runs `--sandbox workspace-write --ask-for-approval never` without network, in either role.
  It cannot reach the agwinterm pipe, so it never types into a pane: it writes mail, and the Claude
  peer's waiter picks it up. That is why one side must be Claude.
- The Reviewer writes only under `.agrevloop/` and `review-runs/`.
- The Author never commits or pushes. After each approved task it stages with `git add -A`, so the
  next review is exactly `git diff`.
- A phase that is not approved after round 3 stops and waits for the human.
