#!/usr/bin/env python3
"""agr - the agrevloop mailbox for one git checkout.

A thin front for agworkbench's vendored transport (agmsg, peerchat, wb.py wait-mail). It pins
the mailbox to <checkout>/.agrevloop/ and the box to the caller's role, so neither agent depends
on environment variables surviving into its tool shell.

  agr.py --as claude init                    # create the mailbox, register both panes
  agr.py --as claude doctor
  agr.py --as claude send --to codex --kind review-request --subject "..." --body-file F --nudge
  agr.py --as codex  send --to claude --kind review --subject "..." --body-file F
  agr.py --as codex  read <id>
  agr.py --as claude list
  agr.py --as claude wait [--timeout MIN]    # exit 0 on mail, 3 on timeout, 2 on bad setup
  agr.py --as claude status active|blocked|completed|idle [--sound]

Any other subcommand is passed to agmsg.py unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HUB_DIR = ".agrevloop"
# The review skill persists its runs in review-runs/ at the checkout root for `incremental`.
EXCLUDED = (f"/{HUB_DIR}/", "/review-runs/")
BOXES = ("claude", "codex")


def die(message: str, code: int = 2) -> None:
    print(f"agr: {message}", file=sys.stderr)
    raise SystemExit(code)


def workbench_lib() -> Path:
    root = os.environ.get("AGWORKBENCH") or str(Path(__file__).resolve().parents[2] / "agworkbench")
    lib = Path(root) / "lib"
    if not (lib / "agmsg.py").is_file():
        die(f"agworkbench not found at {root}; clone yeroo/agworkbench there or set AGWORKBENCH")
    return lib


def find_up(start: Path, name: str) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / name).exists():
            return folder
    return None


def hub_dir() -> Path:
    """The mailbox of the checkout the caller stands in. Found by walking up, not by git: the
    reviewer's sandbox may run as a user git refuses to trust."""
    if os.environ.get("AI_HUB"):
        return Path(os.environ["AI_HUB"]).resolve()
    root = find_up(Path.cwd(), HUB_DIR)
    if root is None:
        die(f"no {HUB_DIR}/ above {Path.cwd()}; the author runs `agr.py --as claude init` first")
    return root / HUB_DIR


def env_for(box: str, hub: Path, lib: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"AI_HUB": str(hub), "AI_BOX": box, "AGWORKBENCH": str(lib.parent)})
    return env


def run(script: Path, args: list[str], env: dict[str, str]) -> int:
    return subprocess.run([sys.executable, str(script), *args], env=env).returncode


def init(lib: Path) -> int:
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode:
        die("init must run inside a git checkout")
    root = Path(top.stdout.strip())
    hub = root / HUB_DIR
    (hub / "reviews").mkdir(parents=True, exist_ok=True)

    exclude = subprocess.run(["git", "rev-parse", "--git-path", "info/exclude"],
                             capture_output=True, text=True, cwd=root).stdout.strip()
    exclude_path = (root / exclude) if exclude else None
    if exclude_path:
        exclude_path.parent.mkdir(parents=True, exist_ok=True)
        lines = exclude_path.read_text(encoding="utf-8").splitlines() if exclude_path.exists() else []
        missing = [entry for entry in EXCLUDED if entry not in lines]
        if missing:
            with exclude_path.open("a", encoding="utf-8") as out:
                out.write("".join(f"{entry}\n" for entry in missing))

    sys.path.insert(0, str(lib))
    os.environ.update(env_for("claude", hub, lib))
    import agw  # noqa: E402

    mine = agw.my_pane()
    if not mine:
        die("no AGWINTERM_PANE_ID: run init from the author's agwinterm pane")
    located = agw.find_pane(mine, agw.tree())
    if not located:
        die(f"own pane {mine} is not in the agwinterm tree")
    peers = [pane for pane in agw.panes_of(located[1]) if pane != mine]
    if len(peers) != 1:
        die("this session needs exactly one split pane with Codex in it")

    env = env_for("claude", hub, lib)
    agmsg = lib / "agmsg.py"
    if run(agmsg, ["register", "claude", "--tool", "claude", "--role", "author", "--cwd", str(root)], env):
        return 1
    if run(agmsg, ["register", "codex", "--tool", "codex", "--role", "reviewer",
                   "--pane", peers[0], "--cwd", str(root)], env):
        return 1
    print(f"mailbox: {hub}")
    print(f"author pane: {mine}  reviewer pane: {peers[0]}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] != "--as" or argv[1] not in BOXES:
        die("usage: agr.py --as claude|codex <command> [args]")
    box, command, rest = argv[1], argv[2], argv[3:]
    lib = workbench_lib()

    if command == "init":
        if box != "claude":
            die("only the author runs init")
        return init(lib)

    hub = hub_dir()
    env = env_for(box, hub, lib)
    if command == "wait":
        return run(lib / "wb.py", ["wait-mail", "--box", box, *rest], env)
    if command == "status":
        if box != "claude":
            die("the reviewer's sandbox cannot reach agwinterm; status is the author's")
        sys.path.insert(0, str(lib))
        import agw  # noqa: E402

        if not rest:
            die("status needs active|blocked|completed|idle")
        agw.set_status(rest[0], sound="--sound" in rest[1:])
        return 0
    if command == "send" and box == "codex" and "--nudge" in rest:
        die("the reviewer never nudges: its sandbox cannot type into a pane, the author's waiter wakes it")
    extra = ["--box", box] if command in ("list", "read", "archive") and "--box" not in rest else []
    return run(lib / "agmsg.py", [command, *rest, *extra], env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
