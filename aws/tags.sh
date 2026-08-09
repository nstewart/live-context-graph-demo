#!/bin/bash
# Resolve the ownership tags required by the RequireTagsScratch SCP.
#
# The scratch account denies creation of taggable resources unless the `owner`,
# `reason`, `team`, and `deleteAfter` tags are all present as *request* tags
# (see MaterializeInc/i2#3620). Sourced by deploy.sh and debug.sh so the
# preflight check and the deploy resolve tags identically.
#
# Overrides, in precedence order:
#   OWNER_EMAIL        - defaults to `git config user.email`
#   REASON             - defaults to "Freshmart Demo"
#   TEAM               - defaults to "Field Engineering"
#   DELETE_AFTER       - explicit ISO8601 timestamp; wins over DELETE_AFTER_HOURS
#   DELETE_AFTER_HOURS - hours from now, defaults to 24

OWNER_EMAIL="${OWNER_EMAIL:-$(git config user.email 2>/dev/null || echo "")}"
REASON="${REASON:-Freshmart Demo}"
TEAM="${TEAM:-Field Engineering}"
DELETE_AFTER_HOURS="${DELETE_AFTER_HOURS:-24}"
DELETE_AFTER="${DELETE_AFTER:-}"

if [[ -z "$OWNER_EMAIL" ]]; then
  echo "Error: cannot resolve the required 'owner' tag." >&2
  echo "  Set it explicitly:  make up-agent-aws OWNER_EMAIL=you@materialize.com" >&2
  echo "  Or configure git:   git config --global user.email you@materialize.com" >&2
  exit 1
fi

if [[ "$OWNER_EMAIL" != *@* ]]; then
  echo "Error: OWNER_EMAIL must be an email address (got '${OWNER_EMAIL}')." >&2
  echo "  The scratch account SCP expects 'owner' to be an email." >&2
  exit 1
fi

if [[ -z "$TEAM" ]]; then
  echo "Error: TEAM cannot be empty (required 'team' tag)." >&2
  exit 1
fi

if [[ -z "$REASON" ]]; then
  echo "Error: REASON cannot be empty (required 'reason' tag)." >&2
  exit 1
fi

# Compute deleteAfter as an ISO8601 UTC timestamp, matching the format
# bin/scratch writes in MaterializeInc/materialize (%Y-%m-%dT%H:%M:%SZ).
if [[ -z "$DELETE_AFTER" ]]; then
  if [[ ! "$DELETE_AFTER_HOURS" =~ ^[0-9]+$ ]] || [[ "$DELETE_AFTER_HOURS" -eq 0 ]]; then
    echo "Error: DELETE_AFTER_HOURS must be a positive integer (got '${DELETE_AFTER_HOURS}')." >&2
    exit 1
  fi
  if date -u -v+1H +%Y >/dev/null 2>&1; then
    # BSD date (macOS)
    DELETE_AFTER=$(date -u -v+"${DELETE_AFTER_HOURS}"H +%Y-%m-%dT%H:%M:%SZ)
  else
    # GNU date (Linux)
    DELETE_AFTER=$(date -u -d "+${DELETE_AFTER_HOURS} hours" +%Y-%m-%dT%H:%M:%SZ)
  fi
fi

# Escape a value for embedding in a JSON string literal.
json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}
