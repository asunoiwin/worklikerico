#!/bin/bash
# checkup.sh —— Linux 日常安全体检（纯只读，不改任何配置）
#
# 用法: bash checkup.sh [输出文件]
#
# 设计原则：按"国内服务器实际被入侵的原因"排序，不按 CVE 严重程度排序。
# 绝大多数沦陷不是因为没打补丁，是因为服务开在公网上没设密码。

OUT="${1:-/tmp/checkup_$(hostname)_$(date +%Y%m%d_%H%M%S).txt}"
exec > >(tee "$OUT") 2>&1

RISK_HIGH=0; RISK_MID=0
hi()  { echo "  ✗ [高危] $*"; RISK_HIGH=$((RISK_HIGH+1)); }
mid() { echo "  ! [中危] $*"; RISK_MID=$((RISK_MID+1)); }
ok()  { echo "  ✓ $*"; }
sec() { echo; echo "━━━ $1 ━━━"; }

echo "安全体检  主机=$(hostname)  时间=$(date)"
echo "系统: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2)  内核: $(uname -r)"
[ "$(id -u)" != "0" ] && echo "! 非 root 运行：读不到 shadow、其他用户家目录、部分进程，检查结果不完整，建议 sudo"

# ============================================================
# 1. 网络暴露面 —— 头号入侵原因，排第一位
# ============================================================
sec "1. 对公网暴露的服务（最高优先级）"

# 高危服务：这些一旦开在公网且无密码，等于把 root 送人
# 格式 端口|说明（不用关联数组，兼容 bash 3.x）
DANGER="6379|Redis（未授权可直接写 SSH 公钥拿 root）
2375|Docker API（未授权等于宿主机 root）
2376|Docker API TLS
27017|MongoDB
9200|Elasticsearch
11211|Memcached
5432|PostgreSQL
3306|MySQL
873|Rsync
111|RPCbind
2181|Zookeeper
9000|PHP-FPM / Portainer
5601|Kibana
8161|ActiveMQ
7001|WebLogic"

LISTEN=$(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null)
PUBLIC_FOUND=0
while IFS='|' read -r port desc; do
  [ -n "$port" ] || continue
  if echo "$LISTEN" | grep -qE "(0\.0\.0\.0|\[::\]|\*):$port "; then
    hi "端口 $port 监听在所有网卡 —— $desc"
    PUBLIC_FOUND=1
  fi
done <<< "$DANGER"
[ $PUBLIC_FOUND = 0 ] && ok "未发现高危服务监听公网地址"

echo
echo "  全部监听端口："
echo "$LISTEN" | tail -n +2 | awk '{print "    "$4"  "$NF}' | sort -u | head -30

# Redis 未授权实测（比看端口更准）
if command -v redis-cli >/dev/null 2>&1 && echo "$LISTEN" | grep -q ":6379 "; then
  if timeout 3 redis-cli -h 127.0.0.1 ping 2>/dev/null | grep -q PONG; then
    hi "Redis 无需密码即可访问 —— 这是国内挖矿木马第一大入口"
  else
    ok "Redis 已设置访问密码"
  fi
fi

# Docker API 未授权实测
if echo "$LISTEN" | grep -qE "(0\.0\.0\.0|\*):2375 "; then
  hi "Docker API 未加密暴露 —— 任何人可创建特权容器接管宿主机"
fi

# ============================================================
# 2. SSH 配置 —— 第二大入侵原因（弱密码爆破）
# ============================================================
sec "2. SSH 安全配置"
SC=/etc/ssh/sshd_config
if [ -f "$SC" ]; then
  # 用 [[:space:]] 而非 \s —— BSD grep 不支持 \s
  getcfg() { grep -iE "^[[:space:]]*$1[[:space:]]" "$SC" 2>/dev/null | grep -v "^[[:space:]]*#" | tail -1 | awk '{print $2}'; }

  DEF=""   # 配置项未显式设置时的标记，保持纯 ASCII 避免编码问题
  P=$(getcfg PermitRootLogin);        [ -z "$P" ] && { P=yes; DEF=" [未配置，走默认值]"; }
  A=$(getcfg PasswordAuthentication); [ -z "$A" ] && A=yes
  E=$(getcfg PermitEmptyPasswords);   [ -z "$E" ] && E=no
  PORT=$(getcfg Port);                [ -z "$PORT" ] && PORT=22

  case "$P" in yes|prohibit-password) [ "$P" = yes ] && hi "允许 root 直接登录$DEF —— 爆破目标明确" || ok "root 仅允许密钥登录" ;; *) ok "已禁止 root 直登" ;; esac
  case "$A" in yes) hi "允许密码登录 —— 可被暴力爆破，建议改密钥登录" ;; *) ok "已禁用密码登录，仅密钥" ;; esac
  case "$E" in yes) hi "允许空密码登录" ;; *) ok "已禁止空密码" ;; esac
  [ "$PORT" = "22" ] && mid "SSH 使用默认端口 22 —— 换非标端口可挡掉绝大多数自动化扫描"

  # 危险配置：登录时执行任意命令
  HOOKS=$(grep -iE "^\s*(ForceCommand|AuthorizedKeysCommand)" "$SC" 2>/dev/null)
  [ -n "$HOOKS" ] && while read -r l; do
    [ -n "$l" ] && mid "存在登录命令钩子（可能是后门）：$l"
  done <<< "$HOOKS"
else
  echo "  (未找到 sshd_config)"
fi

# 爆破迹象（无传统日志文件的系统回退到 journald）
auth_failures() {
  if [ -f /var/log/auth.log ] || [ -f /var/log/secure ]; then
    grep -h "Failed password" /var/log/secure /var/log/auth.log 2>/dev/null
  else
    journalctl -q _COMM=sshd --since "-7 days" 2>/dev/null | grep "Failed password"
  fi
}
FAILED=$(auth_failures | wc -l)
if [ "$FAILED" -gt 1000 ]; then
  hi "日志中有 $FAILED 次登录失败 —— 正在被持续爆破"
  echo "     来源 IP TOP5："
  auth_failures | \
    awk '{for(i=1;i<=NF;i++) if($i=="from") print "       "$(i+1)}' | sort | uniq -c | sort -rn | head -5
elif [ "$FAILED" -gt 0 ]; then
  mid "日志中有 $FAILED 次登录失败"
fi

# 防爆破工具
if command -v fail2ban-client >/dev/null 2>&1; then
  ok "已安装 fail2ban"
else
  [ "$A" = "yes" ] && hi "未装 fail2ban 且允许密码登录 —— 爆破无任何拦截"
fi

# ============================================================
# 3. 账号安全
# ============================================================
sec "3. 账号安全"

ROOTS=$(awk -F: '$3==0 && $1!="root" {print $1}' /etc/passwd)
[ -n "$ROOTS" ] && hi "存在 root 权限的其他账号（后门特征）：$ROOTS" || ok "仅 root 拥有 UID 0"

EMPTY=$(awk -F: '$2=="" {print $1}' /etc/shadow 2>/dev/null)
[ -n "$EMPTY" ] && hi "空密码账号：$EMPTY" || ok "无空密码账号"

echo "  可登录账号："
grep -vE "nologin|/bin/false|/bin/sync" /etc/passwd | grep -v "^#" | awk -F: '{print "    "$1" (uid="$3", shell="$7")"}'

echo "  拥有 sudo 权限："
grep -hE "^[^#].*ALL" /etc/sudoers /etc/sudoers.d/* 2>/dev/null | grep -v "^Defaults" | sed 's/^/    /' | head -10

# SSH 公钥（后门最常见形态，改密码清不掉）
echo "  已授权的 SSH 公钥："
FOUND_KEY=0
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] && [ -s "$f" ] && {
    FOUND_KEY=1
    n=$(grep -c . "$f")
    echo "    $f （$n 个）"
    awk '{print "      "$NF}' "$f" 2>/dev/null | head -5
  }
done
[ $FOUND_KEY = 1 ] && mid "请逐个核对上述公钥是否本人添加 —— 陌生公钥即后门，改密码无效"
[ $FOUND_KEY = 0 ] && ok "未配置 SSH 公钥"

# ============================================================
# 4. 已知木马残留
# ============================================================
sec "4. 已知木马痕迹"
FEED="$(dirname "$0")/../feeds/malware.txt"
[ -f "$FEED" ] || FEED="$(dirname "$0")/feeds/malware.txt"
if [ -f "$FEED" ]; then
  HIT=0
  for mk in $(grep '^marker:' "$FEED" | cut -d: -f2-); do
    [ -e "$mk" ] && { hi "命中木马标志物：$mk"; HIT=1; }
  done
  for p in $(grep '^path:' "$FEED" | cut -d: -f2-); do
    if [ -f "$p" ]; then hi "存在恶意文件路径：$p"; HIT=1
    elif [ -d "$p" ] && [ -n "$(find "$p" -maxdepth 1 -type f -perm -100 2>/dev/null | head -1)" ]; then
      hi "恶意藏身目录中发现可执行文件：$p"; HIT=1
    fi
  done
  [ $HIT = 0 ] && ok "未发现已知木马文件痕迹"
else
  echo "  (特征库未找到，跳过)"
fi

[ -s /etc/ld.so.preload ] && hi "/etc/ld.so.preload 非空 —— rootkit 特征" || ok "ld.so.preload 正常"
[ -d /usr/bin/dpkgd ] && hi "/usr/bin/dpkgd 存在 —— 盖茨木马特征，系统命令已被替换"

# ============================================================
# 5. 持久化审计
# ============================================================
sec "5. 定时任务与自启动"
SUSP=0
for f in /var/spool/cron/* /var/spool/cron/crontabs/* /etc/crontab /etc/cron.d/*; do
  [ -f "$f" ] || continue
  m=$(grep -vE "^\s*#|^\s*$" "$f" 2>/dev/null | grep -E "curl|wget|base64|/dev/tcp|/tmp/|/dev/shm|\|.*(sh|bash)")
  [ -n "$m" ] && { hi "可疑定时任务 → $f"; echo "$m" | sed 's/^/      /'; SUSP=1; }
done
[ $SUSP = 0 ] && ok "定时任务未见异常"

NEW_SVC=$(find /etc/systemd/system -name "*.service" -mtime -30 2>/dev/null)
[ -n "$NEW_SVC" ] && { mid "近 30 天新增的 systemd 服务，请确认是否本人添加："; echo "$NEW_SVC" | sed 's/^/      /'; }

# ============================================================
# 6. 文件权限
# ============================================================
sec "6. 文件权限"
SUID=$(find / -xdev -perm -4000 -type f 2>/dev/null | grep -vE "^/(usr/)?(bin|sbin|lib|lib64)/" | head -10)
[ -n "$SUID" ] && { mid "标准目录之外的 SUID 文件（提权后门常见形态）："; echo "$SUID" | sed 's/^/      /'; } || ok "SUID 文件均位于标准系统目录"

WW=$(find /etc /usr/bin /usr/sbin -xdev -perm -0002 -type f 2>/dev/null | head -5)
[ -n "$WW" ] && { mid "系统目录下存在任何人可写的文件："; echo "$WW" | sed 's/^/      /'; }

# ============================================================
# 7. 补丁状态
# ============================================================
sec "7. 系统补丁"
if command -v apt-get >/dev/null 2>&1; then
  N=$(apt-get -s upgrade 2>/dev/null | grep -c "^Inst")
  S=$(apt-get -s upgrade 2>/dev/null | grep "^Inst" | grep -ci security)
  [ "$S" -gt 0 ] && mid "$N 个可更新包，其中 $S 个安全更新" || ok "无待安装的安全更新（共 $N 个可更新包）"
elif command -v yum >/dev/null 2>&1; then
  N=$(yum check-update -q 2>/dev/null | grep -c .)
  mid "$N 个包可更新（用 yum updateinfo list security 看安全更新）"
fi

if command -v trivy >/dev/null 2>&1; then
  ok "已安装 Trivy，可执行深度漏洞扫描：trivy rootfs --severity HIGH,CRITICAL /"
else
  echo "  (未装 Trivy —— 想要逐个软件包的 CVE 清单需安装它)"
fi

# ============================================================
# 汇总
# ============================================================
echo
echo "════════════════════════════════════════"
echo " 体检完成：高危 $RISK_HIGH 项，中危 $RISK_MID 项"
echo " 报告：$OUT"
echo "════════════════════════════════════════"
if [ $RISK_HIGH -gt 0 ]; then
  echo " 先修高危项。国内服务器沦陷主因排序："
  echo "   1) 数据库/中间件开公网无密码   2) SSH 弱密码爆破   3) 应用漏洞   4) 未打补丁"
  echo " 前两项占绝大多数，补丁反而排最后。"
fi
