#!/bin/bash
# harden.sh —— 清除木马之后：堵后门、封入口、防复发
#
# 用法:
#   bash harden.sh            # 只诊断 + 输出待执行命令（默认，安全）
#   bash harden.sh --apply    # 执行其中不会中断业务的那部分
#
# ⚠ 与 killswitch.sh 的默认行为相反：
#   killswitch 默认动手（杀错进程重启服务即可恢复）
#   harden   默认不动手（改错 SSH 配置可能导致再也连不上，且这类机器多半没有带外通道）

APPLY=0
[ "$1" = "--apply" ] && APPLY=1

# 非 root 读不到 shadow、装不了包、改不了 sshd，很多检查会静默跳过。
# 默认只出建议不动手，非 root 也能看，但要说清结果不全。
[ "$(id -u)" != "0" ] && echo "! 非 root 运行：PAM 校验、空密码检查、包重装等会跳过或失败，建议 sudo"

TS=$(date +%Y%m%d_%H%M%S)
OUT="/root/harden_$TS.txt"
[ -w /root ] || OUT="/tmp/harden_$TS.txt"
exec > >(tee "$OUT") 2>&1

TODO=0
sec()  { echo; echo "━━━ $1 ━━━"; }
need() { echo "  ✗ $*"; TODO=$((TODO+1)); }
ok()   { echo "  ✓ $*"; }
cmd()  { echo "      $ $*"; }
run()  { if [ $APPLY = 1 ]; then eval "$*" && echo "      [已执行] $*"; else echo "      $ $*"; fi; }

echo "后门封堵  主机=$(hostname)  时间=$(date)  模式=$([ $APPLY = 1 ] && echo 执行 || echo 仅建议)"

# ============================================================
# 1. SSH 公钥后门 —— 最高优先级
# ============================================================
sec "1. SSH 公钥后门（改密码对它无效）"
echo "  木马写入的公钥不受改密码影响，不清掉等于门一直开着。"
echo
FOUND=0
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] && [ -s "$f" ] || continue
  FOUND=1
  echo "  文件：$f"
  n=0
  while read -r line; do
    [ -n "$line" ] || continue
    n=$((n+1))
    echo "    [$n] ${line:0:40}... 注释=$(echo "$line" | awk '{print $NF}')"
  done < "$f"
  cp "$f" "${f}.bak_${TS}" 2>/dev/null && echo "    （已备份 → ${f}.bak_${TS}）"
done
if [ $FOUND = 1 ]; then
  need "逐行核对上面每个公钥的来历，删掉不认识的"
  echo "    确认后删除某一行："
  cmd "sed -i '3d' /root/.ssh/authorized_keys   # 删第 3 行"
  echo "    或全部清空重新添加（确保你当前是密码登录，否则会断开）："
  cmd "> /root/.ssh/authorized_keys"
else
  ok "未发现已配置的 SSH 公钥"
fi

# 冷门的 SSH 后门位置
grep -iE "^\s*(ForceCommand|AuthorizedKeysCommand|PermitUserRC)" /etc/ssh/sshd_config 2>/dev/null | while read -r l; do
  need "sshd_config 存在命令钩子（登录即执行任意命令）：$l"
done
for f in /etc/ssh/sshrc /root/.ssh/rc; do
  [ -f "$f" ] && need "登录触发脚本存在，检查内容：$f"
done

# ============================================================
# 2. 账号后门
# ============================================================
sec "2. 账号后门"
R=$(awk -F: '$3==0 && $1!="root" {print $1}' /etc/passwd)
if [ -n "$R" ]; then
  need "存在 root 权限的其他账号：$R"
  for u in $R; do cmd "userdel -r $u"; done
else
  ok "仅 root 拥有 UID 0"
fi

E=$(awk -F: '$2=="" {print $1}' /etc/shadow 2>/dev/null)
[ -n "$E" ] && { need "空密码账号：$E"; for u in $E; do cmd "passwd -l $u"; done; } || ok "无空密码账号"

# 近期新建的账号
NEW=$(find /home -maxdepth 1 -mindepth 1 -type d -mtime -30 2>/dev/null)
[ -n "$NEW" ] && { echo "  近 30 天新增的家目录（确认是否本人创建）："; echo "$NEW" | sed 's/^/      /'; }

echo
need "改掉所有账号密码（木马可能已经把明文密码回传）"
cmd "passwd root"
echo "    有其他账号的逐个改。改完立刻测试新会话能登录，再关掉当前会话。"

# ============================================================
# 3. PAM 后门 —— 常规扫描发现不了
# ============================================================
sec "3. PAM 后门（万能密码）"
echo "  木马会替换认证模块，植入一个无视密码的万能口令。用包管理器校验文件完整性："
if command -v rpm >/dev/null 2>&1; then
  BAD=$(rpm -V pam 2>/dev/null | grep -E "^..5")
  [ -n "$BAD" ] && { need "PAM 模块文件已被篡改："; echo "$BAD" | sed 's/^/      /'; cmd "yum reinstall pam"; } || ok "PAM 模块完整性正常"
elif command -v dpkg >/dev/null 2>&1; then
  BAD=$(dpkg -V libpam-modules 2>/dev/null)
  [ -n "$BAD" ] && { need "PAM 模块文件已被篡改："; echo "$BAD" | sed 's/^/      /'; cmd "apt-get install --reinstall libpam-modules"; } || ok "PAM 模块完整性正常"
else
  echo "  (无包管理器可校验，手工比对 /lib*/security/ 下文件时间)"
fi
NEWPAM=$(find /lib*/security /usr/lib*/security -name "*.so" -newer /etc/hostname 2>/dev/null | head -5)
[ -n "$NEWPAM" ] && { need "比系统安装时间新的 PAM 模块（可疑）："; echo "$NEWPAM" | sed 's/^/      /'; }

# ============================================================
# 4. 被替换的系统命令
# ============================================================
sec "4. 系统命令是否被替换"
if [ -d /usr/bin/dpkgd ]; then
  need "/usr/bin/dpkgd 存在 —— 盖茨木马把干净的原始命令备份在这里，标准路径下的是假的"
  for c in ps netstat lsof ss; do
    [ -f "/usr/bin/dpkgd/$c" ] && cmd "cp -f /usr/bin/dpkgd/$c \$(which $c) && chmod 755 \$(which $c)"
  done
else
  if command -v rpm >/dev/null 2>&1; then
    BAD=$(rpm -Vf /bin/ps /bin/netstat /usr/bin/top 2>/dev/null | grep -E "^..5" | head -5)
    [ -n "$BAD" ] && { need "系统命令被修改："; echo "$BAD" | sed 's/^/      /'; cmd "yum reinstall procps-ng net-tools"; } || ok "系统命令完整性正常"
  elif command -v dpkg >/dev/null 2>&1; then
    BAD=$(dpkg -V procps net-tools 2>/dev/null | head -5)
    [ -n "$BAD" ] && { need "系统命令被修改："; echo "$BAD" | sed 's/^/      /'; cmd "apt-get install --reinstall procps net-tools"; } || ok "系统命令完整性正常"
  fi
fi

[ -s /etc/ld.so.preload ] && {
  need "/etc/ld.so.preload 非空 —— 用户态 rootkit 仍在"
  cat /etc/ld.so.preload | sed 's/^/      /'
  cmd "chattr -i /etc/ld.so.preload; > /etc/ld.so.preload"
  echo "      清完必须重启相关服务，已加载的进程仍带着劫持库在跑"
}

# ============================================================
# 5. 入口封堵 —— 不做这步必然复发
# ============================================================
sec "5. 封堵入口（不做这步一定会再中）"

LISTEN=$(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null)

check_expose() {
  local port=$1 name=$2 fix=$3
  if echo "$LISTEN" | grep -qE "(0\.0\.0\.0|\[::\]|\*):$port "; then
    need "${name} 监听公网（${port}）—— 国内挖矿木马主要入口"
    echo "      $fix"
    return 0
  fi
  return 1
}

EXPOSED=0
check_expose 6379  "Redis"      "改 /etc/redis.conf：bind 127.0.0.1 + requirepass 强密码 + protected-mode yes" && EXPOSED=1
check_expose 2375  "Docker API" "关掉 -H tcp://0.0.0.0:2375，改用本地 socket 或启用 TLS" && EXPOSED=1
check_expose 27017 "MongoDB"    "改 bindIp: 127.0.0.1 并开启认证" && EXPOSED=1
check_expose 9200  "Elasticsearch" "改 network.host: 127.0.0.1 并启用安全模块" && EXPOSED=1
check_expose 11211 "Memcached"  "启动参数加 -l 127.0.0.1" && EXPOSED=1
[ $EXPOSED = 0 ] && ok "未发现高危服务监听公网"

echo
echo "  云安全组（比机器内的 iptables 可靠——木马拿到 root 能改 iptables，改不了云控制台）："
echo "      只放行业务必需端口，数据库/中间件端口一律只对内网开放"

# SSH 爆破入口（无传统日志文件的系统回退到 journald）
auth_failures() {
  if [ -f /var/log/auth.log ] || [ -f /var/log/secure ]; then
    grep -h "Failed password" /var/log/secure /var/log/auth.log 2>/dev/null
  else
    journalctl -q _COMM=sshd --since "-7 days" 2>/dev/null | grep "Failed password"
  fi
}
FAILED=$(auth_failures | wc -l)
if [ "$FAILED" -gt 500 ]; then
  need "日志中 $FAILED 次登录失败 —— 入口极可能就是 SSH 爆破"
  echo "    爆破来源 TOP5："
  auth_failures | \
    awk '{for(i=1;i<=NF;i++) if($i=="from") print "       "$(i+1)}' | sort | uniq -c | sort -rn | head -5
fi

# ============================================================
# 6. 防复发加固
# ============================================================
sec "6. 防复发"

if command -v fail2ban-client >/dev/null 2>&1; then
  ok "已安装 fail2ban"
else
  need "未安装 fail2ban —— 爆破无任何拦截"
  if command -v apt-get >/dev/null 2>&1; then
    run "apt-get install -y fail2ban && systemctl enable --now fail2ban"
  elif command -v yum >/dev/null 2>&1; then
    run "yum install -y epel-release fail2ban && systemctl enable --now fail2ban"
  fi
fi

SC=/etc/ssh/sshd_config
PR=$(grep -iE "^\s*PermitRootLogin\s" $SC 2>/dev/null | tail -1 | awk '{print $2}')
PA=$(grep -iE "^\s*PasswordAuthentication\s" $SC 2>/dev/null | tail -1 | awk '{print $2}')

echo
echo "  SSH 加固（⚠ 这两项改错会导致再也连不上，脚本不会自动执行）："
[ "$PR" != "no" ] && {
  need "允许 root 直接登录"
  cmd "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' $SC"
}
[ "$PA" != "no" ] && {
  need "允许密码登录（可被爆破）"
  echo "      改密钥登录前必须先验证密钥能用！顺序："
  cmd "1) 本地生成密钥：ssh-keygen -t ed25519"
  cmd "2) 传上来：ssh-copy-id -i ~/.ssh/id_ed25519.pub user@本机"
  cmd "3) 另开一个窗口测试密钥能登录成功"
  cmd "4) 确认成功后再改：sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' $SC"
  cmd "5) systemctl reload sshd   （用 reload 不用 restart，现有会话不断）"
}
echo "      改完务必：保留当前会话不要退出，另开窗口验证能登录，再关旧会话。"

# ============================================================
# 7. 横向影响
# ============================================================
sec "7. 横向排查"
echo "  同一入口通常导致批量沦陷。清完这台，其他机器会把它重新打回来。"
echo
echo "  必查："
echo "    · 同网段其他机器是否有相同症状（跑 killswitch.sh --dry-run）"
echo "    · 本机 ~/.ssh/known_hosts 里的机器 —— 木马常沿这个列表横向移动"
[ -f /root/.ssh/known_hosts ] && echo "      本机 known_hosts 有 $(grep -c . /root/.ssh/known_hosts 2>/dev/null) 条记录"
echo "    · 是否全网同一套密码（一台沦陷 = 全网沦陷）"

# ============================================================
# 汇总
# ============================================================
echo
echo "════════════════════════════════════════"
echo " 待处理 $TODO 项    报告：$OUT"
echo "════════════════════════════════════════"
echo
echo " 清除效果验证（清完不代表干净）："
echo "   1. 立刻重跑：bash killswitch.sh --dry-run   → 应无命中"
echo "   2. 重启机器后再跑一次                       → 持久化没清干净的会在这步现形"
echo "   3. 观察 24 小时 CPU 与出向流量               → 恢复正常才算清干净"
echo "   4. 三步都过了，再考虑恢复对外服务"
