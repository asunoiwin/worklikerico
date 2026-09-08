#!/usr/bin/env bash
set -euo pipefail

SCRIPT=$(cd "$(dirname "$0")/.." && pwd)/wait_for_listener.sh
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

cat >"$TMP/systemctl" <<'SH'
#!/usr/bin/env bash
[[ "${MOCK_ACTIVE:-1}" == 1 && "$1 $2" == 'is-active --quiet' ]]
SH
cat >"$TMP/ss" <<'SH'
#!/usr/bin/env bash
printf 'LISTEN 0 128 0.0.0.0:38463 0.0.0.0:*\n'
SH
chmod +x "$TMP/systemctl" "$TMP/ss"

PATH="$TMP:$PATH" "$SCRIPT" example.service 38463 1 tcp | grep -q '^ready '
PATH="$TMP:$PATH" "$SCRIPT" example.service 38463 1 udp | grep -q '^ready '
if PATH="$TMP:$PATH" "$SCRIPT" example.service 38464 1 tcp >/dev/null 2>&1; then
  printf 'expected timeout for absent port\n' >&2
  exit 1
fi
if PATH="$TMP:$PATH" "$SCRIPT" example.service invalid 1 tcp >/dev/null 2>&1; then
  printf 'expected validation failure for invalid port\n' >&2
  exit 1
fi
if MOCK_ACTIVE=0 PATH="$TMP:$PATH" "$SCRIPT" example.service 38463 1 tcp >/dev/null 2>&1; then
  printf 'expected failure for inactive service\n' >&2
  exit 1
fi
printf 'wait_for_listener tests passed\n'
