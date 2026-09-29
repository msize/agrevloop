# agrevloop

Claude Code writes an OpenSpec change, Codex reviews every step, in one agwinterm split. Phase 1 is
the proposal with spec deltas, phase 2 the tasks, phase 3 the implementation task by task. Each step
goes back and forth until Codex approves, at most three rounds. The human passes the gates and
commits at the end.

Two thin skills carry the protocol. The transport is agworkbench's vendored, fail-closed
tooling: `agmsg` (a file mailbox), `peerchat` (the doorbell that types one pointer line into a
provably empty composer) and `wb.py wait-mail` (Claude's background waiter).

| piece | what |
|---|---|
| `skills/claude/agrevloop-author` | Claude's side: phases, rounds, gates, staging checkpoints |
| `skills/codex/agrevloop-reviewer` | Codex's side: reviews with the skill set in `REVIEW_SKILL`, answers by mail |
| `bin/agr.py` | one wrapper for both: mailbox at `<checkout>/.agrevloop/`, box per role |
| `bin/agrevloop-codex` | starts Codex sandboxed, with the mailbox in its tool environment |

## Requirements

- [yeroo/agwinterm](https://github.com/yeroo/agwinterm) with `agwintermctl` on PATH, Git Bash, Python 3.10+
- [yeroo/agworkbench](https://github.com/yeroo/agworkbench) cloned next to this repo, or `AGWORKBENCH` set
- Claude Code, Codex CLI, OpenSpec CLI, and a Codex review skill (see How to review in the reviewer skill)

## Install

```bash
REVIEW_SKILL='$<plugin>:<review-skill>' ./install.sh   # how Codex invokes your review skill
export PATH="<path-to-agrevloop>/bin:$PATH"   # for agrevloop-codex
```

## Use

1. In the project checkout, open an agwinterm split.
2. Right pane: `agrevloop-codex`. It waits for mail.
3. Left pane: start `claude` and say `/agrevloop-author add-retry-policy gates=p1`, or describe
   the change instead of naming it.

Claude runs `agr.py --as claude init`, which creates `.agrevloop/`, adds it and `review-runs/` to
`.git/info/exclude`, and registers both panes. From there each request reaches Codex as a
`Chat from Claude:` pointer and each review wakes Claude through its background waiter.

`.git/info/exclude` is the checkout's own ignore file: it works like `.gitignore` but is never
committed, so the project's `.gitignore` stays untouched and nobody else sees the entries.
`git check-ignore -v .agrevloop/` shows the rule.

## How it is bounded

- Codex runs `--sandbox workspace-write --ask-for-approval never` without network. It cannot reach
  the agwinterm pipe, so it never types into a pane: it writes mail, Claude's waiter picks it up.
- Codex writes only under `.agrevloop/` and `review-runs/`.
- Claude never commits or pushes. After each approved task it stages with `git add -A`, so the
  next review is exactly `git diff`.
- A phase that is not approved after round 3 stops and waits for the human.
