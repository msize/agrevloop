#!/usr/bin/env python3
"""agr - the agrevloop mailbox for one git checkout.

A thin front for agworkbench's vendored transport (agmsg, peerchat, wb.py wait-mail). It pins
the mailbox to <checkout>/.agrevloop/ and the box to the caller's role, so neither agent depends
on environment variables surviving into its tool shell.

Either role can be played by Claude Code or by Codex, but not both by Codex: Codex's sandbox
cannot reach agwinterm, so it can neither ring a pane nor be woken by anything but a ring.

  agr.py --as author init --tool claude      # create the mailbox, register this pane and its tool
  agr.py --as reviewer init --tool codex     # the same for the other pane (the launchers do it)
  agr.py --as author doctor
  agr.py --as author send --to reviewer --kind review-request --subject "..." --body-file F
  agr.py --as reviewer send --to author --kind review --subject "..." --body-file F
  agr.py --as reviewer read <id>
  agr.py --as author list
  agr.py --as author wait [--timeout MIN]    # exit 0 on mail, 3 on timeout, 2 on bad setup
  agr.py --as author status active|blocked|completed|idle [--sound]

`send` rings the recipient's pane when the recipient is Codex, and leaves a Claude recipient to
its own background waiter. Any other subcommand is passed to agmsg.py unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HUB_DIR = ".agrevloop"
# The review skill persists its runs in review-runs/ at the checkout root for `incremental`.
EXCLUDED = (f"/{HUB_DIR}/", "/review-runs/")
PEER = {"author": "reviewer", "reviewer": "author"}
TOOLS = ("claude", "codex")


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
    Codex sandbox may run as a user git refuses to trust."""
    if os.environ.get("AI_HUB"):
        return Path(os.environ["AI_HUB"]).resolve()
    root = find_up(Path.cwd(), HUB_DIR)
    if root is None:
        die(f"no {HUB_DIR}/ above {Path.cwd()}; start both agents with agrevloop-claude or "
            f"agrevloop-codex, or run `agr.py --as <role> init --tool <tool>` first")
    return root / HUB_DIR


def env_for(box: str, hub: Path, lib: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.update({"AI_HUB": str(hub), "AI_BOX": box, "AGWORKBENCH": str(lib.parent)})
    return env


def load(lib: Path, name: str, env: dict[str, str]):
    """Import an agworkbench module with this mailbox and box in the environment."""
    os.environ.update(env)
    if str(lib) not in sys.path:
        sys.path.insert(0, str(lib))
    module = __import__(name)
    if name == "hub":
        module.reload_paths()
    return module


def run(script: Path, args: list[str], env: dict[str, str]) -> int:
    return subprocess.run([sys.executable, str(script), *args], env=env).returncode


def tool_of(lib: Path, env: dict[str, str], box: str) -> str | None:
    return (load(lib, "hub", env).lookup(box) or {}).get("tool")


def init(box: str, rest: list[str], lib: Path) -> int:
    if len(rest) != 2 or rest[0] != "--tool" or rest[1] not in TOOLS:
        die("usage: agr.py --as author|reviewer init --tool claude|codex")
    tool = rest[1]
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

    env = env_for(box, hub, lib)
    agw = load(lib, "agw", env)
    mine = agw.my_pane()
    if not mine:
        die(f"no AGWINTERM_PANE_ID: run init from the {box}'s agwinterm pane")
    located = agw.find_pane(mine, agw.tree())
    if not located:
        die(f"own pane {mine} is not in the agwinterm tree")
    peers = [pane for pane in agw.panes_of(located[1]) if pane != mine]
    if len(peers) != 1:
        die("this session needs exactly one split pane for the other agent")

    if run(lib / "agmsg.py", ["register", box, "--tool", tool, "--role", box, "--cwd", str(root)], env):
        return 1
    print(f"mailbox: {hub}")
    print(f"{box}: {tool} on pane {mine}")
    peer = load(lib, "hub", env).lookup(PEER[box])
    if not peer:
        print(f"{PEER[box]}: not registered yet, start it in pane {peers[0]}")
    elif peer.get("pane") != peers[0]:
        print(f"{PEER[box]}: registered on pane {peer.get('pane')}, not on {peers[0]}: restart it there")
    else:
        print(f"{PEER[box]}: {peer.get('tool')} on pane {peers[0]}")
        if tool == "codex" and peer.get("tool") == "codex":
            die("both agents are Codex: neither can wake the other; one side must be Claude")
    return 0


def send(box: str, rest: list[str], lib: Path, env: dict[str, str]) -> int:
    """File the message, and ring the recipient when it has no waiter of its own."""
    if "--nudge" in rest:
        die("agr decides the ring itself: drop --nudge")
    if "--to" not in rest or rest.index("--to") + 1 >= len(rest):
        die("send needs --to author|reviewer")
    to = rest[rest.index("--to") + 1]
    mine, theirs = tool_of(lib, env, box), tool_of(lib, env, to)
    if not mine:
        die(f"{box} is not registered: run `agr.py --as {box} init --tool <tool>` from its pane")
    if not theirs:
        die(f"{to} is not registered: ask the human to start it in the other pane")
    extra: list[str] = []
    if theirs == "codex":
        if mine == "codex":
            die("both agents are Codex: nobody can wake the recipient; one side must be Claude")
        extra = ["--nudge"]
    return run(lib / "agmsg.py", ["send", *rest, *extra], env)


def main(argv: list[str]) -> int:
    if len(argv) < 3 or argv[0] != "--as" or argv[1] not in PEER:
        die("usage: agr.py --as author|reviewer <command> [args]")
    box, command, rest = argv[1], argv[2], argv[3:]
    lib = workbench_lib()

    if command == "init":
        return init(box, rest, lib)

    hub = hub_dir()
    env = env_for(box, hub, lib)
    if command == "wait":
        return run(lib / "wb.py", ["wait-mail", "--box", box, *rest], env)
    if command == "status":
        if tool_of(lib, env, box) == "codex":
            die("Codex's sandbox cannot reach agwinterm; status is for a Claude pane")
        if not rest:
            die("status needs active|blocked|completed|idle")
        load(lib, "agw", env).set_status(rest[0], sound="--sound" in rest[1:])
        return 0
    if command == "send":
        return send(box, rest, lib, env)
    extra = ["--box", box] if command in ("list", "read", "archive") and "--box" not in rest else []
    return run(lib / "agmsg.py", [command, *rest, *extra], env)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
