#!/usr/bin/env python3
"""agr - the agrevloop mailbox for one git checkout.

A thin front for agworkbench's vendored transport (agmsg, peerchat, wb.py wait-mail). It pins
the mailbox to <checkout>/.agrevloop/ and the box to the caller's role, so neither agent depends
on environment variables surviving into its tool shell.

Either role can be played by Claude Code or by Codex, but not both by Codex: Codex's sandbox
cannot reach agwinterm, so it can neither ring a pane nor be woken by anything but a ring.

  agr.py --as author init --tool claude --with codex   # mailbox, this pane, a vertical split
  agr.py --as reviewer init --tool codex               # register the other pane (the launchers do)
  agr.py --as author doctor
  agr.py --as author send --to reviewer --kind review-request --subject "..." --body-file F
  agr.py --as reviewer send --to author --kind review --subject "..." --body-file F
  agr.py --as reviewer read <id>
  agr.py --as author list
  agr.py --as author wait [--timeout MIN]    # exit 0 on mail, 3 on timeout, 2 on bad setup
  agr.py --as author status active|blocked|completed|idle [--sound]

`init --with` makes sure the author's session is split left/right and remembers which tool
reviews. The reviewer is started in the other pane, at the checkout root, by the launcher next to
this file: by the author's first `send` when the author is Claude, so it starts with the request
already in its inbox, and by `init` itself when the author is Codex, whose sandbox could not.

`send` rings the recipient's pane when the recipient is Codex, and leaves a Claude recipient to
its own background waiter. Any other subcommand is passed to agmsg.py unchanged.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HUB_DIR = ".agrevloop"
PAIR_FILE = "pair.json"
# The review skill persists its runs in review-runs/ at the checkout root for `incremental`.
EXCLUDED = (f"/{HUB_DIR}/", "/review-runs/")
PEER = {"author": "reviewer", "reviewer": "author"}
TOOLS = ("claude", "codex")
BIN = Path(__file__).resolve().parent

# A pane is typed into only when its last rows prove a shell prompt and nothing like an agent.
AGENT_MARKS = re.compile(r"esc to interrupt|bypass permissions|for shortcuts|Ask Codex|Working|"
                         r"\[y/N\]|Do you trust|\(y/n\)")
RULE = re.compile("^\\s*[-─━—]{10,}\\s*$", re.M)
FRESH_PANE_WAIT = 30.0
REGISTER_WAIT = 60.0


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


# --- the split ------------------------------------------------------------------------------

def ctl(agw, *args: str):
    """One agwintermctl call through the CLI, for verbs agw has no wrapper for."""
    done = subprocess.run([agw.ctl_path(), *args, "--json"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=15)
    try:
        envelope = json.loads(done.stdout)
    except json.JSONDecodeError:
        die(f"agwintermctl {' '.join(args)}: {(done.stderr or done.stdout).strip()}")
    if not envelope.get("ok"):
        die(f"agwintermctl {' '.join(args)}: {envelope.get('error')}")
    return envelope.get("result")


def own_session(agw) -> tuple[str, dict]:
    mine = agw.my_pane()
    if not mine:
        die("no AGWINTERM_PANE_ID: run this from an agwinterm pane")
    located = agw.find_pane(mine, agw.tree())
    if not located:
        die(f"own pane {mine} is not in the agwinterm tree")
    return mine, located[1]


def peer_pane(agw, *, split: bool) -> tuple[str | None, bool]:
    """The other pane of this session, and whether it was just made. With `split`, a one-pane
    session is split left/right and a top/bottom split is turned left/right."""
    mine, session = own_session(agw)
    panes = agw.panes_of(session)
    others = [pane for pane in panes if pane != mine]
    if len(others) > 1:
        die("this session has more than two panes")
    if not split:
        return (others[0] if others else None), False
    if others:
        if session.get("axis", "vertical") != "vertical":
            ctl(agw, "session", "split", "on", "--axis", "vertical", "--target", mine)
        return others[0], False
    ctl(agw, "session", "split", "on", "--axis", "vertical", "--target", mine)
    for _ in range(30):
        time.sleep(0.3)
        session = own_session(agw)[1]
        panes = agw.panes_of(session)
        others = [pane for pane in panes if pane != mine]
        if others:
            # The split takes the keyboard focus; the human was typing in this pane.
            if session.get("active") and session.get("focusedPane") != panes.index(mine):
                ctl(agw, "session", "focus", "other")
            return others[0], True
    die("the split did not appear")
    return None, False


def shell_of(text: str) -> str | None:
    """powershell, cmd or bash when the pane shows an idle prompt of that shell, else None."""
    rows = [row.rstrip() for row in text.splitlines() if row.strip()]
    if not rows:
        return None
    frame = "\n".join(rows[-15:])
    if AGENT_MARKS.search(frame) or RULE.search(frame):
        return None
    last = rows[-1]
    if re.match(r"^PS [A-Za-z]:\\.*>$", last):
        return "powershell"
    if re.match(r"^[A-Za-z]:\\.*>$", last):
        return "cmd"
    if re.search(r"[$#]$", last):
        return "bash"
    return None


def wait_shell(agw, pane: str, seconds: float) -> str | None:
    deadline = time.monotonic() + seconds
    while True:
        shell = shell_of(agw.pane_text(pane))
        if shell or time.monotonic() >= deadline:
            return shell
        time.sleep(0.3)


def posix(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    match = re.match(r"^([A-Za-z]):/(.*)$", text)
    return f"/{match.group(1).lower()}/{match.group(2)}" if match else text


def git_bash() -> str:
    """Git for Windows' bash.exe, the one that sets up its own PATH: <git root>/bin/bash.exe."""
    explicit = os.environ.get("AGREVLOOP_BASH")
    if explicit:
        return explicit
    exec_path = subprocess.run(["git", "--exec-path"], capture_output=True, text=True).stdout.strip()
    candidate = Path(exec_path).parents[2] / "bin" / "bash.exe" if exec_path else None
    if not candidate or not candidate.is_file():
        die("cannot find Git Bash; set AGREVLOOP_BASH to its bash.exe")
    return str(candidate)


def start_command(tool: str, root: Path, shell: str) -> str:
    inner = f"cd '{posix(root)}' && '{posix(BIN / f'agrevloop-{tool}')}' reviewer"
    if "'" in str(root) + str(BIN):
        die("a path with a single quote cannot be typed into a pane")
    if shell == "bash":
        return inner
    bash = git_bash()
    return f"& '{bash}' -lc \"{inner}\"" if shell == "powershell" else f"\"{bash}\" -lc \"{inner}\""


def start_reviewer(lib: Path, env: dict[str, str], agw, pane: str, tool: str, root: Path,
                   shell: str) -> None:
    """Type the reviewer launcher into the other pane and wait until it has registered."""
    hub = load(lib, "hub", env)
    before = hub.now_iso()
    agw.type_into(pane, start_command(tool, root, shell) + "\n")
    print(f"reviewer: starting {tool} in pane {pane}")
    deadline = time.monotonic() + REGISTER_WAIT
    while time.monotonic() < deadline:
        entry = hub.lookup("reviewer") or {}
        if entry.get("pane") == pane and entry.get("last_seen", "") >= before:
            print(f"reviewer: {tool} registered on pane {pane}")
            return
        time.sleep(1)
    die(f"the reviewer did not register within {REGISTER_WAIT:.0f}s; look at pane {pane}", 1)


def read_pair(hub: Path) -> dict:
    try:
        return json.loads((hub / PAIR_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# --- commands -------------------------------------------------------------------------------

def init(box: str, rest: list[str], lib: Path) -> int:
    options = dict(zip(rest[::2], rest[1::2]))
    tool, partner = options.get("--tool"), options.get("--with")
    if len(rest) % 2 or set(options) - {"--tool", "--with"} or tool not in TOOLS or \
            (partner is not None and (box != "author" or partner not in TOOLS)):
        die("usage: agr.py --as author init --tool claude|codex [--with claude|codex]\n"
            "       agr.py --as reviewer init --tool claude|codex")
    if tool == "codex" and partner == "codex":
        die("both agents would be Codex: neither could wake the other; use --with claude")
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
    mine = own_session(agw)[0]
    pane, fresh = peer_pane(agw, split=partner is not None)
    if not pane:
        die("this session needs a split pane for the other agent")

    if run(lib / "agmsg.py", ["register", box, "--tool", tool, "--role", box, "--cwd", str(root)], env):
        return 1
    print(f"mailbox: {hub}")
    print(f"{box}: {tool} on pane {mine}")
    peer = load(lib, "hub", env).lookup(PEER[box]) or {}
    if partner:
        (hub / PAIR_FILE).write_text(json.dumps({"reviewer": partner}), encoding="utf-8")
        shell = wait_shell(agw, pane, FRESH_PANE_WAIT if fresh else 3.0)
        if shell:
            if tool == "codex":
                start_reviewer(lib, env, agw, pane, partner, root, shell)
            else:
                print(f"reviewer: {partner} starts in pane {pane} with the first request")
            return 0
        if peer.get("pane") != pane:
            die(f"pane {pane} is neither a shell prompt nor the reviewer; leave it at a shell prompt "
                f"or start the reviewer there: {posix(BIN / f'agrevloop-{partner}')} reviewer")
        if peer.get("tool") != partner:
            die(f"pane {pane} already runs a {peer.get('tool')} reviewer, not {partner}")
    if not peer:
        print(f"{PEER[box]}: not registered yet, start it in pane {pane}")
    elif peer.get("pane") != pane:
        print(f"{PEER[box]}: registered on pane {peer.get('pane')}, not on {pane}: restart it there")
    else:
        print(f"{PEER[box]}: {peer.get('tool')} on pane {pane}")
        if tool == "codex" and peer.get("tool") == "codex":
            die("both agents are Codex: neither can wake the other; one side must be Claude")
    return 0


def send(box: str, rest: list[str], lib: Path, env: dict[str, str]) -> int:
    """File the message, and ring the recipient when it has no waiter of its own. A Claude author
    whose reviewer pane is still a shell starts the reviewer after filing, so it finds the mail."""
    if "--nudge" in rest:
        die("agr decides the ring itself: drop --nudge")
    if "--to" not in rest or rest.index("--to") + 1 >= len(rest):
        die("send needs --to author|reviewer")
    to = rest[rest.index("--to") + 1]
    mine, theirs = tool_of(lib, env, box), tool_of(lib, env, to)
    if not mine:
        die(f"{box} is not registered: run `agr.py --as {box} init --tool <tool>` from its pane")

    partner = read_pair(Path(env["AI_HUB"])).get("reviewer")
    if box == "author" and to == "reviewer" and mine == "claude" and partner:
        agw = load(lib, "agw", env)
        pane, fresh = peer_pane(agw, split=True)
        shell = wait_shell(agw, pane, FRESH_PANE_WAIT if fresh else 3.0)
        if shell:
            # Filed before the reviewer registers: agmsg's warning about that is expected here.
            filed = subprocess.run([sys.executable, str(lib / "agmsg.py"), "send", *rest, "--force"],
                                   env=env, stderr=subprocess.PIPE, text=True)
            sys.stderr.write("".join(line for line in filed.stderr.splitlines(True)
                                     if "is not a registered box" not in line))
            if filed.returncode:
                return 1
            start_reviewer(lib, env, agw, pane, partner, Path(env["AI_HUB"]).parent, shell)
            return 0
        if (load(lib, "hub", env).lookup(to) or {}).get("pane") != pane:
            die(f"pane {pane} is neither a shell prompt nor the reviewer; leave it at a shell prompt "
                f"or start the reviewer there: {posix(BIN / f'agrevloop-{partner}')} reviewer")

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
