#!/usr/bin/env bash
# Install the agrevloop skills for Claude Code and Codex, and put bin/ on the user PATH hint.
# Safe to re-run: the skills are overwritten from this checkout, nothing else is touched.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workbench="${AGWORKBENCH:-$(cd "$here/.." && pwd)/agworkbench}"
agr="$(cygpath -m "$here/bin/agr.py")"
review_skill="${REVIEW_SKILL:?set REVIEW_SKILL to how Codex invokes its review skill, e.g. \$plugin:review}"

[ -f "$workbench/lib/agmsg.py" ] || {
  echo "install: agworkbench not found at $workbench (git clone https://github.com/yeroo/agworkbench there, or set AGWORKBENCH)" >&2
  exit 2
}

install_skill() {
  local src="$1" dst="$2"
  mkdir -p "$dst"
  sed -e "s|@AGR@|$agr|g" -e "s|@REVIEW_SKILL@|$review_skill|g" "$src/SKILL.md" > "$dst/SKILL.md"
  echo "installed $dst/SKILL.md"
}

install_skill "$here/skills/claude/agrevloop-author" "$HOME/.claude/skills/agrevloop-author"
install_skill "$here/skills/codex/agrevloop-reviewer" "$HOME/.codex/skills/agrevloop-reviewer"
chmod +x "$here/bin/agrevloop-codex" "$here/bin/agr.py"

case ":$PATH:" in
  *":$here/bin:"*) ;;
  *) echo "add to PATH to get agrevloop-codex: export PATH=\"$here/bin:\$PATH\"" ;;
esac
