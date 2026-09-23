#!/usr/bin/env bash
# Set up a daily-work repo in the given directory (default: here). Never overwrites:
# an existing CLAUDE.md gets only the template's missing ## sections, an existing
# .gitignore only its missing lines. Prints one line per file.
set -euo pipefail
source "$(dirname "$0")/lib.sh"
P="$TEMPLATES/project"

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

for f in CLAUDE.md README.md .gitignore .env.example pyproject.toml; do
  if [ ! -e "$f" ]; then
    cp "$P/$f" "$f"; echo "$f: copied"
  elif [ "$f" = CLAUDE.md ] && n=$(append_sections "$P/$f" "$f") && [ "$n" -gt 0 ]; then
    echo "$f: appended $n missing sections"
  elif [ "$f" = .gitignore ] && n=$(append_lines "$P/$f" "$f") && [ "$n" -gt 0 ]; then
    echo "$f: appended $n missing lines"
  else
    echo "$f: skipped"
  fi
done

if [ -e areas/_inbox/.gitkeep ]; then
  echo "areas/_inbox/.gitkeep: skipped"
else
  mkdir -p areas/_inbox && : > areas/_inbox/.gitkeep && echo "areas/_inbox/.gitkeep: copied"
fi

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { git init -q; echo "git: initialized"; }

echo "Next: /daily-work:task <area> <slug>, or /grill-with-docs aimed at the repo to seed the glossary"
