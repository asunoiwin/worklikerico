#!/usr/bin/env bash
set -euo pipefail

[[ $(uname -s) == Linux ]] || { printf 'unsupported: Linux target required\n' >&2; exit 2; }
[[ -r /etc/os-release ]] || { printf 'unsupported: /etc/os-release missing\n' >&2; exit 2; }
. /etc/os-release

id=${ID,,}
like=${ID_LIKE:-}
case " $id $like " in
  *ubuntu*|*debian*) family=debian ;;
  *centos*|*rhel*|*rocky*|*almalinux*|*fedora*) family=rhel ;;
  *) printf 'unsupported Linux distribution: ID=%s ID_LIKE=%s\n' "$ID" "${ID_LIKE:-}" >&2; exit 3 ;;
esac

case "$(uname -m)" in
  x86_64|amd64) arch=amd64 ;;
  aarch64|arm64) arch=arm64 ;;
  *) arch=$(uname -m) ;;
esac

if command -v apt-get >/dev/null 2>&1; then package_manager=apt-get
elif command -v dnf >/dev/null 2>&1; then package_manager=dnf
elif command -v yum >/dev/null 2>&1; then package_manager=yum
else package_manager=missing
fi

printf 'os=%s\nfamily=%s\narch=%s\nkernel=%s\npackage_manager=%s\n' \
  "${PRETTY_NAME:-$ID}" "$family" "$arch" "$(uname -r)" "$package_manager"
printf 'init=%s\n' "$(ps -p 1 -o comm= 2>/dev/null || true)"
printf 'sudo=%s\n' "$(command -v sudo >/dev/null 2>&1 && printf available || printf missing)"
printf 'curl=%s\nwget=%s\n' \
  "$(command -v curl >/dev/null 2>&1 && printf available || printf missing)" \
  "$(command -v wget >/dev/null 2>&1 && printf available || printf missing)"
printf 'bbr_current=%s\n' "$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || printf unknown)"
printf 'bbr_available=%s\n' "$(sysctl -n net.ipv4.tcp_available_congestion_control 2>/dev/null || printf unknown)"
printf 'ip_forward=%s\n' "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || printf unknown)"
printf 'iptables=%s\nnft=%s\n' \
  "$(command -v iptables >/dev/null 2>&1 && printf available || printf missing)" \
  "$(command -v nft >/dev/null 2>&1 && printf available || printf missing)"

if command -v curl >/dev/null 2>&1 && curl -fsSIL --connect-timeout 4 --max-time 8 https://raw.githubusercontent.com/ >/dev/null 2>&1; then
  printf 'github_raw=reachable\n'
else
  printf 'github_raw=blocked_or_unreachable\n'
fi

printf '\n[listeners]\n'
if command -v ss >/dev/null 2>&1; then
  ss -H -lntup 2>/dev/null || ss -H -lntu 2>/dev/null || true
elif command -v netstat >/dev/null 2>&1; then
  netstat -lntup 2>/dev/null || true
else
  printf 'listener_tool=missing\n'
fi
