# Shared helpers for daily-work scripts. Sourced, not run.

TEMPLATES="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/templates"
SLUG_RE='^[a-z0-9-]+$'

refuse() { echo "refused: $*"; exit 1; }

# The plugin's Python runs through uv, on the Python that /daily-work:init set up (README
# "Requirements" under Setup). Never the system python3: on Windows that can be the Microsoft Store
# placeholder, on macOS a shim that opens an install dialog. Nothing is downloaded here.
# uv's installer puts it in ~/.local/bin, which a desktop app's PATH can leave out; on Windows
# that is under %USERPROFILE%, which need not be Git Bash's $HOME.
uv_bin() {
  local u win=
  [ -n "${USERPROFILE:-}" ] && win="$(cygpath -u "$USERPROFILE" 2>/dev/null)/.local/bin/uv.exe"
  for u in "$(command -v uv 2>/dev/null)" "$HOME/.local/bin/uv" "$win"; do
    [ -n "$u" ] && [ -x "$u" ] && { echo "$u"; return 0; }
  done
  return 1
}
py() {
  local u
  u=$(uv_bin) || return 1
  "$u" run --no-project --managed-python --no-python-downloads --quiet python "$@"
}
python_ready() {
  local u
  u=$(uv_bin) && "$u" python find --managed-python >/dev/null 2>&1
}

# One line when there is no Python, so a missing setup is never silent.
python_note() {
  python_ready && return 0
  echo "daily-work: no Python set up, so this run sends no telemetry and no content log. Run /daily-work:init to set it up."
}

# Usage telemetry (README "Telemetry"). Never fails and never waits for the network.
telemetry() {
  [ "${DAILY_WORK_TELEMETRY:-}" = 0 ] && return 0
  py "$(dirname "${BASH_SOURCE[0]}")/telemetry.py" "$@" 2>/dev/null || true
}

# Content logging (README "Content logging"). Does nothing when DAILY_WORK_CONTENT=0.
content() {
  [ "${DAILY_WORK_CONTENT:-}" = 0 ] && return 0
  py "$(dirname "${BASH_SOURCE[0]}")/content.py" "$@" 2>/dev/null || true
}

# A random version 4 UUID, from /dev/urandom; needs no Python.
new_uuid() {
  local h
  h=$(od -An -N16 -tx1 /dev/urandom | tr -d ' \n')
  printf '%s-%s-4%s-%x%s-%s\n' "${h:0:8}" "${h:8:4}" "${h:13:3}" $(( (0x${h:16:1} & 3) | 8 )) "${h:17:3}" "${h:20:12}"
}

# Copy template $1 to $2, filling <project>, <slug>, <date>, <title>, <id> from env,
# and replacing the <description> placeholder line with env ASK.
fill() {
  mkdir -p "$(dirname "$2")"
  awk '
    function sub_all(s, tok, val,   i, out) {
      out = ""
      while ((i = index(s, tok)) > 0) { out = out substr(s, 1, i - 1) val; s = substr(s, i + length(tok)) }
      return out s
    }
    $0 == "<description>" { print ENVIRON["ASK"]; next }
    {
      s = sub_all($0, "<project>", ENVIRON["PROJECT"])
      s = sub_all(s, "<slug>", ENVIRON["SLUG"])
      s = sub_all(s, "<title>", ENVIRON["TITLE"])
      s = sub_all(s, "<id>", ENVIRON["ID"])
      print sub_all(s, "<date>", ENVIRON["DATE"])
    }' "$1" > "$2"
}

# Put line $3 at the end of the "## " section $2 of file $1, adding the section if missing.
add_under() {
  [ -f "$1" ] || : > "$1"
  H="$2" LINE="$3" awk '
    { L[NR] = $0 }
    END {
      h = ENVIRON["H"]; line = ENVIRON["LINE"]; s = 0
      for (i = 1; i <= NR; i++) if (L[i] == h) { s = i; break }
      if (!s) {
        for (i = 1; i <= NR; i++) print L[i]
        if (NR && L[NR] != "") print ""
        print h; print line; exit
      }
      last = s
      for (i = s + 1; i <= NR && L[i] !~ /^## /; i++) if (L[i] != "") last = i
      for (i = 1; i <= NR; i++) { print L[i]; if (i == last) print line }
    }' "$1" > "$1.tmp" && mv "$1.tmp" "$1"
}
