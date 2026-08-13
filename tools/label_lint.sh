#!/usr/bin/env bash
# Fail if the default label's brand name is hardcoded in application source.
#
# The leak detector (check_label_leaks.py) proves a LABEL carries no grocery
# vocabulary. This proves the CODE carries no hardcoded brand -- the other way
# white-labeling regresses, when someone types "FreshMart" into a component
# instead of reading it from the active label.
#
# Portable to bash 3.2 (macOS default): no mapfile, no globstar.
set -uo pipefail

cd "$(dirname "$0")/.."

# Customer-visible surfaces only:
#   web/src      - the UI
#   agents/src   - LLM-facing prompts and tool docstrings
#   api/src/main - the OpenAPI docs page (linked from the README, shown in demos)
#
# Deliberately NOT scanned: Python internals in api/, load-generator/, and
# db/scripts. Their module docstrings, class names (FreshMartAPIClient), log
# lines, and comments carry the default brand, but none of it reaches a
# customer -- renaming them would be churn with no demo benefit. If that
# changes, widen this list rather than sprinkling exemptions.
FILES=$(
  { git ls-files web/src agents/src | grep -E '\.(ts|tsx|py)$'
    git ls-files api/src/main.py api/src/demo_label.py; } \
  | grep -vE '\.test\.(ts|tsx)$|(^|/)tests?/|web/src/generated/' \
  || true
)

if [ -z "$FILES" ]; then
  echo "FAIL label_lint matched no source files -- the pathspec is wrong." >&2
  echo "     Refusing to report a vacuous pass." >&2
  exit 1
fi

echo "label-lint: scanning $(printf '%s\n' "$FILES" | wc -l | tr -d ' ') source files"
status=0

# Structural identifiers that are deliberately NOT label-driven, because they are
# data-model shape and a field engineer's mental model depends on them being
# stable: the /freshmart API router prefix, the Postgres database name, and the
# Docker network name. See docs/WHITE_LABELING.md.
STRUCTURAL='/freshmart/|freshmartApi|freshmart-network|pg_database|PG_DATABASE|"freshmart"|freshmart_|_freshmart'

check() {
  pattern="$1"; what="$2"
  hits=$(printf '%s\n' "$FILES" | tr '\n' '\0' | xargs -0 grep -nEi "$pattern" 2>/dev/null \
         | grep -vE "$STRUCTURAL" || true)
  if [ -n "$hits" ]; then
    echo "FAIL $what is hardcoded in application source:"
    printf '%s\n' "$hits" | sed 's/^/  /'
    status=1
  else
    echo "OK   no hardcoded $what"
  fi
}

check 'freshmart' "brand name"
# The order-number prefix is label-driven (vocabulary.order.id_prefix).
check "[\"'\`f]FM-" "order-number prefix"

if [ $status -ne 0 ]; then
  echo
  echo "Read these from the active label instead:"
  echo "  web : import { brand, entity, copy } from '../label'"
  echo "  py  : from demo_label import load_label, order_prefix"
  echo "See docs/WHITE_LABELING.md."
fi

exit $status
