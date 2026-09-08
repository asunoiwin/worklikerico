#!/usr/bin/env bash
# git-diff-to-symbols.sh
# Parse git diff into JSON: { files: [{ path, changed_symbols, hunks }], stats }
#
# Usage:
#   ./git-diff-to-symbols.sh                 # working tree (staged + unstaged)
#   ./git-diff-to-symbols.sh HEAD~3..HEAD    # commit range
#   ./git-diff-to-symbols.sh --staged        # only staged
#
# Output: JSON on stdout. Symbol detection relies on git's funcname hunk header
# (the text after `@@` on hunk lines), which works out-of-box for Java/JS/TS/Go/Python/Rust.

set -euo pipefail

RANGE="${1:-}"
case "$RANGE" in
  --staged) DIFF_CMD=(git diff -U0 --no-color --staged) ;;
  "")       DIFF_CMD=(git diff -U0 --no-color HEAD) ;;
  *)        DIFF_CMD=(git diff -U0 --no-color "$RANGE") ;;
esac

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo '{"error":"not a git repo","files":[],"stats":{"raw_diff_lines":0,"file_count":0}}'
  exit 0
fi

DIFF_OUT="$("${DIFF_CMD[@]}" 2>/dev/null || true)"
if [ -z "$DIFF_OUT" ]; then
  echo '{"files":[],"stats":{"raw_diff_lines":0,"file_count":0,"note":"no diff"}}'
  exit 0
fi

# Extract per-file changed symbols using awk
# git diff hunk format:  @@ -old +new @@ <funcname-context>
# We collect the funcname context after the second @@ on each hunk line.

echo "$DIFF_OUT" | awk '
  BEGIN { file=""; }
  /^diff --git / {
    # diff --git a/path/to/file b/path/to/file
    n = split($0, parts, " ")
    bpath = parts[n]
    sub(/^b\//, "", bpath)
    file = bpath
    files[file] = 1
    next
  }
  /^@@/ {
    if (file == "") next
    # @@ -1,2 +3,4 @@ funcname-context-here
    idx = index($0, "@@")
    rest = substr($0, idx+2)
    idx2 = index(rest, "@@")
    if (idx2 == 0) next
    ctx = substr(rest, idx2+2)
    sub(/^[ \t]+/, "", ctx)
    sub(/[ \t]+$/, "", ctx)
    if (ctx != "") {
      key = file "|" ctx
      if (!(key in seen)) {
        seen[key] = 1
        symbols[file] = symbols[file] "\037" ctx
        hunk_count[file]++
      }
    } else {
      # hunk with no funcname context — still count it
      hunk_count[file]++
    }
  }
  END {
    printf("{\"files\":[")
    first = 1
    for (f in files) {
      if (!first) printf(",")
      first = 0
      printf("{\"path\":\"%s\",\"hunk_count\":%d,\"changed_symbols\":[", f, hunk_count[f]+0)
      s = symbols[f]
      if (s != "") {
        n = split(s, arr, "\037")
        ssep = ""
        for (i = 1; i <= n; i++) {
          sym = arr[i]
          if (sym == "") continue
          gsub(/\\/, "\\\\", sym)
          gsub(/"/, "\\\"", sym)
          printf("%s\"%s\"", ssep, sym)
          ssep = ","
        }
      }
      printf("]}")
    }
    printf("],\"stats\":{")
    file_count = 0
    for (f in files) file_count++
    printf("\"file_count\":%d", file_count)
    printf("}}\n")
  }
'
