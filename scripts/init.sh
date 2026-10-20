#!/usr/bin/env bash
# Set up a daily-work repo in the given directory (default: here). Never overwrites:
# an existing AGENTS.md gets only the template's missing ## sections, an existing
# .gitignore or CLAUDE.md only its missing lines. Prints one line per file.
# AGENTS.md holds the instructions, for every coding agent. Claude Code reads it on its own
# when there is no CLAUDE.md, so none is created; an existing CLAUDE.md gets the @AGENTS.md
# import, because Claude Code then reads CLAUDE.md only.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
P="$TEMPLATES/repo"

cd "${1:-.}"

# Append each "## " section of template $1 that file $2 lacks. Prints how many.
append_sections() {
  local n=0 h
  while IFS= read -r h; do
    grep -qxF -- "$h" "$2" && continue
    [ -s "$2" ] && { [ -z "$(tail -c1 "$2")" ] || echo >> "$2"; echo >> "$2"; }
    H="$h" awk '$0 == ENVIRON["H"] { on = 1 } on && /^## / && $0 != ENVIRON["H"] { exit }
      on { b[++n] = $0 } END { while (n && b[n] == "") n--; for (i = 1; i <= n; i++) print b[i] }' "$1" >> "$2"
    n=$((n + 1))
  done < <(grep -E '^## ' "$1")
  echo "$n"
}

# Append each non-blank line of template $1 that file $2 lacks. Prints how many.
append_lines() {
  local n=0 l
  while IFS= read -r l; do
    [ -z "$l" ] && continue
    grep -qxF -- "$l" "$2" && continue
    [ -s "$2" ] && [ -n "$(tail -c1 "$2")" ] && echo >> "$2"
    printf '%s\n' "$l" >> "$2"
    n=$((n + 1))
  done < "$1"
  echo "$n"
}

for f in AGENTS.md README.md .gitignore .env.example pyproject.toml .claude/settings.json; do
  if [ ! -e "$f" ]; then
    mkdir -p "$(dirname "$f")"; cp "$P/$f" "$f"; echo "$f: copied"
  elif [ "$f" = AGENTS.md ] && n=$(append_sections "$P/$f" "$f") && [ "$n" -gt 0 ]; then
    echo "$f: appended $n missing sections"
  elif [ "$f" = .gitignore ] && n=$(append_lines "$P/$f" "$f") && [ "$n" -gt 0 ]; then
    echo "$f: appended $n missing lines"
  else
    echo "$f: skipped"
  fi
done

if [ -e CLAUDE.md ]; then
  if n=$(append_lines "$P/CLAUDE.md" CLAUDE.md) && [ "$n" -gt 0 ]; then echo "CLAUDE.md: appended $n missing lines"
  else echo "CLAUDE.md: skipped"; fi
fi

for f in tools/.gitkeep; do
  if [ -e "$f" ]; then echo "$f: skipped"; else mkdir -p "$(dirname "$f")" && : > "$f" && echo "$f: copied"; fi
done

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { git init -q; echo "git: initialized"; }

# The Python that telemetry and content logging run on; setup-python.sh makes it.
if ! u=$(uv_bin); then echo "python: missing (no uv)"
elif ! python_ready; then echo "python: missing (uv $("$u" --version | cut -d' ' -f2), no Python yet)"
else echo "python: $(py -c 'import platform; print(platform.python_version())') through uv"; fi

echo "Next: the brief skill, with <project> <describe the task>. In Claude Code: /daily-work:brief <project> <describe the task>"
