# Shared helpers for daily-work scripts. Sourced, not run.

TEMPLATES="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/templates"
SLUG_RE='^[a-z0-9-]+$'

refuse() { echo "refused: $*"; exit 1; }

# Copy template $1 to $2, filling <area>, <slug>, <date>, <title> from env,
# and replacing the Ask placeholder line with env ASK when it is set.
fill() {
  mkdir -p "$(dirname "$2")"
  awk '
    function sub_all(s, tok, val,   i, out) {
      out = ""
      while ((i = index(s, tok)) > 0) { out = out substr(s, 1, i - 1) val; s = substr(s, i + length(tok)) }
      return out s
    }
    $0 == "<What was asked, by whom, by when, in the asker'\''s words.>" && ENVIRON["ASK"] != "" { print ENVIRON["ASK"]; next }
    {
      s = sub_all($0, "<area>", ENVIRON["AREA"])
      s = sub_all(s, "<slug>", ENVIRON["SLUG"])
      s = sub_all(s, "<title>", ENVIRON["TITLE"])
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
