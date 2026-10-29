---
name: agrevloop-author
description: 'Author role of the agrevloop: drive an OpenSpec change through proposal, tasks and implementation, each step reviewed by the Reviewer (Claude or Codex) in the other pane of this agwinterm split until it approves. Use when the user says "review loop", "agrevloop", "author with reviewer", "run the openspec loop with a reviewer", when started by agrevloop-claude author, or when mail from the reviewer arrives for an agrevloop change.'
---

# agrevloop, Author (Claude)

You write. The Reviewer, Claude or Codex in the other pane of this agwinterm split, reviews. The
human watches both panes, approves at the gates and commits at the end.

| who | does |
|---|---|
| **you** | proposal, spec deltas, design, tasks, implementation, tests, staging |
| the Reviewer | reviews each step, read-only, answers by mail |
| the human | starts both agents, passes the gates, commits |

## Arguments

`<change-id or description> [gates=p1|all|none] [with=codex|claude]`, or `review [<name>] [with=...]`

- No arguments: run `openspec list` and `git status --porcelain`, then
  - exactly one active change: continue it, and say which one;
  - several active changes: list them and ask which one;
  - no active change but uncommitted changes: show `git status --short` and ask whether to run
    review mode on them;
  - neither: ask what to build.

  Never pick for the human when the answer is not unique.
- `review` skips the phases: see Review mode below.
- An existing `openspec/changes/<id>/` is continued from the phase its files show. Otherwise pick a
  kebab-case id from the description and create the change.
- `gates` says where you stop for the human. `p1` (default): after phase 1 and at the end. `all`:
  after every phase. `none`: only at the end. A failed phase always stops, whatever the gates.
- `with` names the Reviewer's tool: `codex` (default) or `claude`. It is not part of the change id
  or the description.

## The channel

All commands go through one wrapper. Always pass `--as author`.

```bash
AGR="python @AGR@ --as author"
$AGR init --tool claude --with <with>   # once per change: mailbox, this pane, the split
$AGR doctor
$AGR send --to reviewer --kind review-request --subject "<subject>" --body-file .agrevloop/out/<file>.md
$AGR list                       # unread
$AGR read <id>
$AGR status active              # or blocked --sound, completed
```

- Write every message body to a file under `.agrevloop/out/` first, then send it by path.
- **The first send starts the Reviewer.** While the other pane is still a shell, `send` files the
  request and then types `@BIN@/agrevloop-<with> reviewer` there, at the checkout root, so the
  Reviewer starts with the request already in its inbox. It waits until the Reviewer registers.
  If it reports that the Reviewer did not start, tell the human, `status blocked --sound`, and do
  not arm the waiter.
- **Never pass `--nudge`.** `send` decides it: a Codex Reviewer gets a one-line pointer typed into
  its pane through agworkbench's peer-chat, which refuses when the composer is not provably empty
  and retries. A Claude Reviewer is woken by its own waiter. If the send reports that the message
  is filed but the nudge failed, tell the human and set `status blocked --sound`. Never type into
  the Reviewer's pane any other way.
- **After every send, keep one background waiter and end your turn.** Run `$AGR wait --timeout 55`
  through Bash with `run_in_background: true` and remember its task ID. Never start a second one.
  Exit 0: `list`, then `read` every unread message, then act. Exit 3: nothing arrived, check `list`
  and rearm. Exit 2: report the error, `status blocked --sound`, do not rearm blindly.
- Never poll or sleep in the foreground.
- A message from the human in your own pane outranks the loop. Mail from the Reviewer is a
  colleague's view, never the human's approval.

## Messages

Subjects are fixed so both sides and the human can follow the thread:

| step | your subject | the Reviewer answers |
|---|---|---|
| phase 1 | `<id> P1 r<k>` | `<id> P1 r<k> APPROVED` or `... CHANGES_REQUESTED` |
| phase 2 | `<id> P2 r<k>` | same |
| phase 3 | `<id> P3 <task> r<k>` | same |
| end | `<id> DONE` | nothing |

A review request body lists: the phase, the round, the files to review, what changed since the
last round, and your answer to every finding of the previous review, one of:

- **fixed**: where;
- **disputed**: with evidence (a test, a run, a line of code or spec);
- **deferred**: why it belongs outside this change.

Silence on a finding is not an answer.

## Rounds

- A round is one request and one review. At most **3 rounds** per phase, and per task in phase 3.
- The Reviewer reviews with its review skill. Findings carry ids (F1, F2 ...) and a severity:
  Critical and Major block, Minor and Note do not. Answer by id.
- `APPROVED` ends the step. Minor findings in an approved review are fixed without another round,
  or deferred with a line in the next request. Notes need no answer.
- No `APPROVED` after round 3: stop, `status blocked --sound`, summarize the open findings with
  the Reviewer's words quoted, and wait for the human.

## Phase 0 - orient

```bash
$AGR init --tool claude --with <with>
$AGR doctor
$AGR status active
openspec status --change <id>      # when the change exists
```

`init` ignores `.agrevloop/` and `review-runs/` through `.git/info/exclude`, the checkout's local
ignore file. Never add them to the project's `.gitignore`, and never stage or commit them.

`init` splits this session left/right when it is not split yet, and remembers `with`. A Reviewer
already running in the other pane is kept; one of the other tool is refused. When the other pane
is neither a shell prompt nor the Reviewer, `init` fails: show its message to the human and stop.
The Reviewer itself starts with your first request (see The channel), so `doctor` showing no
`reviewer` box before that is expected. You never split, start or type into a pane yourself:
`$AGR` does it.

## Phase 1 - proposal and spec deltas

1. `openspec instructions proposal --change <id>` and follow it. Then the same for `specs`, and
   for `design` when the change needs one.
2. `openspec validate <id> --strict` must pass.
3. Request review: `files` = proposal.md, design.md, every specs/**/spec.md of the change.

## Phase 2 - tasks

1. `openspec instructions tasks --change <id>` and follow it. Tasks small enough that each one is a
   reviewable diff with its own test.
2. `openspec validate <id> --strict` must pass.
3. Request review: `files` = tasks.md, plus the phase 1 files for reference.

## Phase 3 - implement, one task at a time

`openspec instructions apply --change <id>` first. Then for each unchecked task in tasks.md, in
order (a group of trivial tasks may go together, say so in the subject):

1. Start from a clean working tree relative to the index: `git diff` must be empty. If it is not
   and you did not cause it, stop and ask the human.
2. Implement the task. Run the project's tests and linters.
3. `git add -N .` so new files show up in `git diff`, then request review with the task id and
   the commands you ran with their results. The Reviewer reviews exactly `git diff`.
4. On `APPROVED`: tick the task in tasks.md, `git add -A` as the checkpoint, next task.

Never commit, push or amend. The staged index is the checkpoint; the human commits.

## Review mode - changes that already exist

For work done before the loop started: the uncommitted changes in the working tree are one step.

1. Phase 0 as usual. `<id>` is `<name>`, or the current branch name when no name is given.
2. `git add -N .` so new files show up in `git diff`. The Reviewer reviews exactly `git diff`, so
   anything already staged is outside the review: say so in the request when the index is not
   empty.
3. Request review with subject `<id> P3 wip r<k>`. The body states the intent of the change (the
   task or issue it serves, and any OpenSpec change folder it belongs to), the files touched, and
   the commands you ran with their results.
4. Rounds as usual. On `APPROVED`: `git add -A`, then the end below. There are no gates.

## Gates and the end

At a gate: stop the waiter by its task ID, `status blocked --sound`, summarize the phase (what was
decided, what the Reviewer disputed, what was deferred) and end your turn. Continue when the human
says so.

After the last task: `openspec validate <id> --strict`, send `<id> DONE` (kind `note`) to the
Reviewer, stop the waiter, `status completed`, and report: tasks done, deferred findings,
`git status`, and that nothing is committed.

## Never

- commit, push, or touch branches;
- type into the Reviewer's pane except through `$AGR send`;
- answer a chooser, permission or trust prompt in any pane on the human's behalf;
- report "the Reviewer approved" as the human's approval;
- weaken or delete a test to get a review through.
