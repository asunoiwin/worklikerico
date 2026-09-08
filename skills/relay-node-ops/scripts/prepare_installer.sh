#!/usr/bin/env bash
set -euo pipefail

ROLE=${1:-}
[[ -n "$ROLE" ]] || { printf 'usage: %s bbr|v2ray|gost|iptables|brook [--china-source] [options]\n' "$0" >&2; exit 2; }
shift
case "$ROLE" in
  bbr)
    DEFAULT_URL=https://github.000060000.xyz/tcp.sh
    CHINA_URL=https://cdn.jsdelivr.net/gh/ylx2016/Linux-NetSpeed@master/tcp.sh
    CHINA_FALLBACK_URL=https://ghproxy.net/https://raw.githubusercontent.com/ylx2016/Linux-NetSpeed/master/tcp.sh
    ;;
  v2ray)
    DEFAULT_URL=https://git.io/v2ray.sh
    CHINA_URL=https://cdn.jsdelivr.net/gh/233boy/v2ray@master/install.sh
    CHINA_FALLBACK_URL=https://ghproxy.net/https://raw.githubusercontent.com/233boy/v2ray/master/install.sh
    ;;
  gost)
    DEFAULT_URL=https://raw.githubusercontent.com/KANIKIG/Multi-EasyGost/master/gost.sh
    CHINA_URL=https://cdn.jsdelivr.net/gh/KANIKIG/Multi-EasyGost@master/gost.sh
    CHINA_FALLBACK_URL=https://ghproxy.net/https://raw.githubusercontent.com/KANIKIG/Multi-EasyGost/master/gost.sh
    ;;
  iptables)
    DEFAULT_URL=https://file.goalnowtech.com/iptables-pf.sh
    DEFAULT_FALLBACK_URL=https://raw.githubusercontent.com/ToyoDAdoubiBackup/doubi/master/iptables-pf.sh
    CHINA_URL=https://cdn.jsdelivr.net/gh/ToyoDAdoubiBackup/doubi@master/iptables-pf.sh
    CHINA_FALLBACK_URL=https://ghproxy.net/https://raw.githubusercontent.com/ToyoDAdoubiBackup/doubi/master/iptables-pf.sh
    ;;
  brook)
    DEFAULT_URL=https://raw.githubusercontent.com/monret/brook/master/brook-pf-mod.sh
    CHINA_URL=https://cdn.jsdelivr.net/gh/monret/brook@master/brook-pf-mod.sh
    CHINA_FALLBACK_URL=https://ghproxy.net/https://raw.githubusercontent.com/monret/brook/master/brook-pf-mod.sh
    ;;
  *) printf 'unknown role: %s\n' "$ROLE" >&2; exit 2 ;;
esac

URL=$DEFAULT_URL
FALLBACK_URL=${DEFAULT_FALLBACK_URL:-}
URL_OVERRIDDEN=0
LOCAL_SCRIPT=
INSTALL_DEPS=0
RUN=0
CONFIRM=0
CHINA_SOURCE=0
CACHE_DIR=${RNO_CACHE_DIR:-/var/cache/relay-node-ops}
while (($#)); do
  case "$1" in
    --url) URL=${2:-}; URL_OVERRIDDEN=1; shift ;;
    --local-script) LOCAL_SCRIPT=${2:-}; shift ;;
    --china-source) CHINA_SOURCE=1 ;;
    --install-deps) INSTALL_DEPS=1 ;;
    --run) RUN=1 ;;
    --confirm) CONFIRM=1 ;;
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

[[ $CHINA_SOURCE -eq 0 || $URL_OVERRIDDEN -eq 0 ]] || {
  printf '%s\n' '--china-source cannot be combined with --url' >&2
  exit 2
}

[[ $(uname -s) == Linux ]] || { printf 'unsupported: Linux target required\n' >&2; exit 2; }
[[ $EUID -eq 0 ]] || { printf 'run with sudo or as root\n' >&2; exit 1; }
[[ -r /etc/os-release ]] || { printf '/etc/os-release missing\n' >&2; exit 2; }
. /etc/os-release
case " ${ID,,} ${ID_LIKE:-} " in
  *ubuntu*|*debian*) FAMILY=debian ;;
  *centos*|*rhel*|*rocky*|*almalinux*|*fedora*) FAMILY=rhel ;;
  *) printf 'unsupported Linux distribution: %s\n' "$ID" >&2; exit 3 ;;
esac

if [[ $INSTALL_DEPS -eq 1 ]]; then
  if [[ "$FAMILY" == debian ]]; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl wget
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y ca-certificates curl wget
  else
    yum install -y ca-certificates curl wget
  fi
fi

command -v curl >/dev/null 2>&1 || { printf 'curl missing; rerun with --install-deps\n' >&2; exit 4; }
command -v sha256sum >/dev/null 2>&1 || { printf 'sha256sum missing\n' >&2; exit 4; }
install -d -m 0755 "$CACHE_DIR"
DEST="$CACHE_DIR/$ROLE.sh"
TMP=$(mktemp "$CACHE_DIR/.${ROLE}.XXXXXX")
cleanup() { [[ ! -e "$TMP" ]] || rm -f "$TMP"; }
trap cleanup EXIT

if [[ -n "$LOCAL_SCRIPT" ]]; then
  [[ -s "$LOCAL_SCRIPT" ]] || { printf 'local script missing or empty: %s\n' "$LOCAL_SCRIPT" >&2; exit 5; }
  cp "$LOCAL_SCRIPT" "$TMP"
  SOURCE="local:$LOCAL_SCRIPT"
else
  if [[ $CHINA_SOURCE -eq 1 ]]; then
    URL=$CHINA_URL
    FALLBACK_URL=$CHINA_FALLBACK_URL
  fi
  [[ "$URL" == https://* ]] || { printf 'HTTPS source required\n' >&2; exit 5; }
  if ! EFFECTIVE=$(curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 -o "$TMP" -w '%{url_effective}' "$URL"); then
    if [[ $URL_OVERRIDDEN -eq 0 && -n "$FALLBACK_URL" ]]; then
      printf 'primary source failed; trying reviewed fallback=%s\n' "$FALLBACK_URL" >&2
      EFFECTIVE=$(curl -fsSL --retry 2 --connect-timeout 10 --max-time 120 -o "$TMP" -w '%{url_effective}' "$FALLBACK_URL") || {
        printf 'download failed; fetch on the controller and retry with --local-script\n' >&2
        exit 5
      }
    else
      printf 'download failed; fetch on the controller and retry with --local-script\n' >&2
      exit 5
    fi
  fi
  SOURCE=$EFFECTIVE
fi

[[ -s "$TMP" ]] || { printf 'downloaded script is empty\n' >&2; exit 5; }
bash -n "$TMP" || { printf 'shell syntax check failed\n' >&2; exit 6; }
UPSTREAM_HASH=$(sha256sum "$TMP" | awk '{print $1}')
COMPATIBILITY_ADAPTER=none
if [[ "$ROLE" == brook ]]; then
  [[ $(grep -Fc 'brook_new_ver=$(wget -qO-' "$TMP") -eq 1 ]] || {
    printf 'Brook installer layout changed; review before adapting\n' >&2
    exit 6
  }
  sed -i 's|brook_new_ver=$(wget -qO-.*|brook_new_ver=v20200801|' "$TMP"
  COMPATIBILITY_ADAPTER=brook-relays-v20200801
fi
ADAPTER=none
if [[ $CHINA_SOURCE -eq 1 && "$ROLE" != bbr ]]; then
  ADAPTER=gh-proxy.com
  if ! grep -q '^# relay-node-ops github adapter: gh-proxy.com$' "$TMP"; then
    sed -i \
      -e 's#https://api.github.com/#https://gh-proxy.com/https://api.github.com/#g' \
      -e 's#https://raw.githubusercontent.com/#https://gh-proxy.com/https://raw.githubusercontent.com/#g' \
      -e 's#https://github.com/#https://gh-proxy.com/https://github.com/#g' \
      "$TMP"
    sed -i '1a # relay-node-ops github adapter: gh-proxy.com' "$TMP"
    bash -n "$TMP" || { printf 'adapted script syntax check failed\n' >&2; exit 6; }
  fi
fi
HASH=$(sha256sum "$TMP" | awk '{print $1}')
if [[ -e "$DEST" ]] && ! cmp -s "$TMP" "$DEST"; then
  cp -a "$DEST" "$DEST.previous"
fi
install -m 0700 "$TMP" "$DEST"
rm -f "$TMP"
printf 'linux_family=%s\nrole=%s\nsource_mode=%s\nsource=%s\nupstream_sha256=%s\ngithub_url_adapter=%s\ncompatibility_adapter=%s\nsha256=%s\ncached=%s\n' \
  "$FAMILY" "$ROLE" "$([[ $CHINA_SOURCE -eq 1 ]] && printf china || printf direct)" "$SOURCE" "$UPSTREAM_HASH" "$ADAPTER" "$COMPATIBILITY_ADAPTER" "$HASH" "$DEST"
if [[ $CHINA_SOURCE -eq 1 && "$ROLE" == gost ]]; then
  printf '%s\n' 'gost_note=when prompted for the built-in mainland mirror, answer n; its Aliyun OSS endpoint is unavailable'
fi

if [[ $RUN -ne 1 ]]; then
  printf 'prepared_only=true\nnext=sudo %q %q --local-script %q' "$0" "$ROLE" "$DEST"
  [[ $CHINA_SOURCE -eq 0 ]] || printf ' --china-source'
  printf ' --run --confirm\n'
  exit 0
fi
[[ $CONFIRM -eq 1 ]] || { printf '--run requires --confirm\n' >&2; exit 7; }
printf 'executing_cached_installer=%s\n' "$DEST"
exec bash "$DEST"
