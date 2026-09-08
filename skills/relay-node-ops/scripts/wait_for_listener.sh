#!/usr/bin/env bash
set -euo pipefail

SERVICE=${1:-}
PORT=${2:-}
TIMEOUT=${3:-30}
PROTOCOL=${4:-tcp}

[[ -n "$SERVICE" && "$PORT" =~ ^[0-9]+$ && "$PORT" -ge 1 && "$PORT" -le 65535 ]] || {
  printf 'usage: %s SERVICE PORT [TIMEOUT_SECONDS] [tcp|udp]\n' "$0" >&2
  exit 2
}
[[ "$TIMEOUT" =~ ^[0-9]+$ && "$TIMEOUT" -ge 1 ]] || {
  printf 'invalid timeout: %s\n' "$TIMEOUT" >&2
  exit 2
}
[[ "$PROTOCOL" == tcp || "$PROTOCOL" == udp ]] || {
  printf 'invalid protocol: %s\n' "$PROTOCOL" >&2
  exit 2
}
command -v systemctl >/dev/null 2>&1 || { printf 'systemctl is required\n' >&2; exit 3; }
command -v ss >/dev/null 2>&1 || { printf 'ss is required\n' >&2; exit 3; }

deadline=$((SECONDS + TIMEOUT))
while ((SECONDS < deadline)); do
  if ! systemctl is-active --quiet "$SERVICE"; then
    printf 'service is not active: %s\n' "$SERVICE" >&2
    exit 4
  fi
  if [[ "$PROTOCOL" == tcp ]]; then
    sockets=$(ss -H -lnt 2>/dev/null || true)
  else
    sockets=$(ss -H -lnu 2>/dev/null || true)
  fi
  if awk -v port="$PORT" '$4 ~ (":" port "$") {found=1} END {exit !found}' <<<"$sockets"; then
    printf 'ready service=%s protocol=%s port=%s\n' "$SERVICE" "$PROTOCOL" "$PORT"
    exit 0
  fi
  sleep 1
done

printf 'listener timeout service=%s protocol=%s port=%s timeout=%s\n' "$SERVICE" "$PROTOCOL" "$PORT" "$TIMEOUT" >&2
exit 5
