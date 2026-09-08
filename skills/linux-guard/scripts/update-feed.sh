#!/bin/bash
# update-feed.sh —— 特征库半自动更新（只在维护端跑，不上生产服务器）
#
# 干什么：从 ThreatFox(abuse.ch) 拉近 N 天被标记为 Linux 挖矿/僵尸网络家族的恶意【域名】，
#         过四道安全关，产出一份【待人工确认的候选清单】。确认后才合并进 feeds/malware.txt。
#
# 铁律（别破坏）：
#   1. 只自动更新 domain: 一类。进程名/路径/端口永远人工维护——它们误伤代价高、自动源里也基本没有。
#   2. 产出的是待审清单，不直接改库。人过目 → 手动 --merge 才写入。
#   3. 生产服务器零联网不变：库在维护端合并好，随脚本分发。
#
# 用法：
#   ANNET_KEY 从 abuse.ch 登录后拿，写进 ~/.config/abuse-ch.key（chmod 600）或环境变量 THREATFOX_KEY
#   bash update-feed.sh            # 拉取+过滤，出待审清单，不改库
#   bash update-feed.sh --days 30  # 改拉取窗口（默认 30 天）
#   bash update-feed.sh --merge    # 把上一次产出的待审清单合并进 feeds/malware.txt

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
FEED="$DIR/../feeds/malware.txt"
STAGE="$DIR/../feeds/.candidates.txt"     # 待审清单落地处
DAYS=7   # ThreatFox get_iocs 的 days 上限就是 7，填更大返回 illegal_days
MODE=fetch
while [ $# -gt 0 ]; do
  case "$1" in
    --days) DAYS="$2"; shift 2 ;;
    --merge) MODE=merge; shift ;;
    *) echo "未知参数: $1"; exit 1 ;;
  esac
done

# ---- 密钥 ----
KEY="${THREATFOX_KEY:-}"
[ -z "$KEY" ] && [ -f "$HOME/.config/abuse-ch.key" ] && KEY="$(cat "$HOME/.config/abuse-ch.key")"

# ============================================================
# 关卡 0：合法域名黑名单 —— 这些域名永远不许进库
# 攻击者常把载荷放在 GitHub/网盘/Pastebin，情报源会把这些一并标进去，
# 自动加了等于把半个互联网标成木马。命中这里的候选直接丢弃。
# ============================================================
ALLOWLIST_RE='(^|\.)(github(usercontent)?\.com|githubusercontent\.com|gitlab\.com|bitbucket\.org|githack\.com|raw\.githack\.com|pastebin\.com|paste\.ee|ghostbin\.com|hastebin\.com|gist\.github\.com|amazonaws\.com|s3\.amazonaws\.com|cloudfront\.net|googleusercontent\.com|storage\.googleapis\.com|drive\.google\.com|dropbox\.com|dropboxusercontent\.com|onedrive\.live\.com|1drv\.ms|mega\.nz|mediafire\.com|discord(app)?\.com|cdn\.discordapp\.com|telegram\.org|t\.me|cloudflare\.com|workers\.dev|pages\.dev|netlify\.app|vercel\.app|herokuapp\.com|glitch\.me|repl\.co|ngrok\.io|ngrok-free\.app|duckdns\.org|no-ip\.(com|org)|sourceforge\.net|jsdelivr\.net|unpkg\.com|npmjs\.(com|org)|pypi\.org|bit\.ly|tinyurl\.com|goo\.gl|ipfs\.io|archive\.org|sh\.rustup\.rs|termbin\.com)$'

# 归一化到主域名（e2LD）：hk02.supportxmr.com → supportxmr.com
# 覆盖多数常见公共后缀；少数二级后缀(co.uk 等)保留三段，宁可多留一段也别过度截断误伤
main_domain() {
  local d; d=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')   # macOS bash 3.2 无 ${d,,}
  d="${d#*://}"; d="${d%%/*}"; d="${d%%:*}"          # 去协议/路径/端口
  d="${d#.}"; d="${d%.}"
  case "$d" in
    *.co.uk|*.com.cn|*.org.cn|*.net.cn|*.com.hk|*.com.tw|*.co.jp|*.com.br|*.com.au)
      echo "$d" | awk -F. '{print $(NF-2)"."$(NF-1)"."$NF}' ;;
    *.*)
      echo "$d" | awk -F. '{print $(NF-1)"."$NF}' ;;
    *) echo "$d" ;;
  esac
}

if [ "$MODE" = fetch ]; then
  [ -z "$KEY" ] && { echo "✗ 没有 ThreatFox 密钥。abuse.ch 登录后把 Auth-Key 写进 ~/.config/abuse-ch.key（chmod 600）或 export THREATFOX_KEY=..."; exit 1; }

  echo "→ 从 ThreatFox 拉取近 $DAYS 天 domain 类 IOC ..."
  RAW=$(curl -s --max-time 40 -X POST "https://threatfox-api.abuse.ch/api/v1/" \
        -H "Auth-Key: $KEY" \
        -d "{\"query\":\"get_iocs\",\"days\":$DAYS}")

  if ! echo "$RAW" | grep -q '"query_status": *"ok"'; then
    echo "✗ 拉取失败，返回："; echo "$RAW" | head -c 300; echo; exit 1
  fi

  # 关卡 1：只要 domain 类型、且家族标签像 Linux 侧（elf. 前缀 / miner / xmrig / coinminer / botnet 家族）
  # 用 jq 若装了走 jq，没装退化到 grep/sed（字段固定，可行）
  if command -v jq >/dev/null 2>&1; then
    CAND=$(echo "$RAW" | jq -r '
      .data[]
      | select(.ioc_type=="domain")
      | select((.malware // "" | ascii_downcase) as $m
               | ($m|startswith("elf."))
                 or ($m|test("miner|xmrig|coinminer|kinsing|mirai|gafgyt|tsunami|sysrv|redtail|diicot|prometei|monero")))
      | "\(.ioc)\t\(.malware)\t\(.first_seen // "?")"')
  else
    # 无 jq：粗解析，够用
    CAND=$(echo "$RAW" | tr ',' '\n' | grep -oE '"ioc": *"[^"]+"|"malware": *"[^"]+"' | paste - - 2>/dev/null \
           | sed -E 's/"ioc": *"([^"]+)".*"malware": *"([^"]+)"/\1\t\2\t?/' \
           | grep -iE 'elf\.|miner|xmrig|coinminer|kinsing|mirai|gafgyt|tsunami|sysrv|redtail|diicot|prometei|monero')
  fi

  # 关卡 2：归一化 + 去合法域名 + 去已在库的
  EXIST=$(grep '^domain:' "$FEED" | cut -d: -f2- | tr -d ' ')
  : > "$STAGE"
  seen=""
  while IFS=$'\t' read -r ioc mal first; do
    [ -z "$ioc" ] && continue
    md=$(main_domain "$ioc")
    [ -z "$md" ] && continue
    echo "$md" | grep -qiE "$ALLOWLIST_RE" && continue            # 关卡0：合法域名黑名单
    echo " $EXIST " | grep -q " $md " && continue                 # 已在库
    case " $seen " in *" $md "*) continue ;; esac                 # 本批去重
    seen="$seen $md"
    printf 'domain:%s\t# %s  first_seen=%s\n' "$md" "${mal:-?}" "${first:-?}" >> "$STAGE"
  done <<< "$CAND"

  N=$(grep -c . "$STAGE" 2>/dev/null || echo 0)
  echo
  echo "════ 待审清单（$N 条新域名，尚未入库）════"
  if [ "$N" -gt 0 ]; then
    cat "$STAGE"
    echo
    echo "落地：$STAGE"
    echo "人工过目后，确认全部可信 → bash update-feed.sh --merge 写入特征库"
    echo "（个别不要的，先手动删 $STAGE 里对应行再 --merge）"
  else
    echo "无新增（都已在库或被安全过滤挡掉）。"
  fi
  exit 0
fi

# ---- --merge：把待审清单并入特征库，跑关卡3误伤测试，过了才落盘 ----
if [ "$MODE" = merge ]; then
  [ -s "$STAGE" ] || { echo "没有待审清单（先跑一次不带 --merge 的拉取）。"; exit 1; }

  BAK="$FEED.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$FEED" "$BAK"
  TMP="$FEED.tmp"
  DATESTR=$(date +%Y-%m-%d)

  # 追加到域名区块末尾（文件末尾即可，killswitch/checkup 按前缀 grep，位置无所谓）
  {
    cat "$FEED"
    echo ""
    echo "# ==== ThreatFox 自动拉取合并 ${DATESTR}（已过合法域名过滤+去重+误伤测试）===="
    cut -f1 "$STAGE"
  } > "$TMP"

  # 关卡 3：误伤回归测试 —— 新库里的 name: 条目不能撞上真实进程名
  if bash "$DIR/../../linux-guard/scripts/feed-selftest.sh" "$TMP" 2>/dev/null || \
     bash "$DIR/feed-selftest.sh" "$TMP" 2>/dev/null; then
    mv "$TMP" "$FEED"
    : > "$STAGE"
    echo "✓ 已合并进 ${FEED}（备份 ${BAK}）。误伤测试通过。"
    echo "  下一步：把 feeds/ 和 scripts/ 同步到需要的机器（生产端零联网，库随脚本走）。"
  else
    rm -f "$TMP"
    echo "✗ 误伤测试未通过，已回滚，未改库。检查 $STAGE 里是否混入了危险条目。"
    exit 1
  fi
fi
