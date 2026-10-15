#!/usr/bin/env bash
# Install the agrevloop author and reviewer skills for both Claude Code and Codex, and put bin/ on
# the user PATH hint. Safe to re-run: the skills are overwritten from this checkout, nothing else
# is touched.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
workbench="${AGWORKBENCH:-$(cd "$here/.." && pwd)/agworkbench}"
agr="$(cygpath -m "$here/bin/agr.py")"
codex_review="${CODEX_REVIEW_SKILL:?set CODEX_REVIEW_SKILL to how Codex invokes its review skill, e.g. \$plugin:review}"
claude_review="${CLAUDE_REVIEW_SKILL:?set CLAUDE_REVIEW_SKILL to how Claude Code invokes its review skill, e.g. /plugin:review}"

[ -f "$workbench/lib/agmsg.py" ] || {
  echo "install: agworkbench not found at $workbench (git clone https://github.com/yeroo/agworkbench there, or set AGWORKBENCH)" >&2
  exit 2
}

install_skill() {
  local src="$1" dst="$2" review="$3"
  mkdir -p "$dst"
  sed -e "s|@AGR@|$agr|g" -e "s|@REVIEW_SKILL@|$review|g" "$src/SKILL.md" > "$dst/SKILL.md"
  echo "installed $dst/SKILL.md"
}

for role in author reviewer; do
  install_skill "$here/skills/claude/agrevloop-$role" "$HOME/.claude/skills/agrevloop-$role" "$claude_review"
  install_skill "$here/skills/codex/agrevloop-$role" "$HOME/.codex/skills/agrevloop-$role" "$codex_review"
done
chmod +x "$here/bin/agrevloop-claude" "$here/bin/agrevloop-codex" "$here/bin/agr.py"

case ":$PATH:" in
  *":$here/bin:"*) ;;
  *) echo "add to PATH to get agrevloop-claude and agrevloop-codex: export PATH=\"$here/bin:\$PATH\"" ;;
esac
