#!/bin/bash
# killswitch.sh —— 发包/挖矿一键止损
#
# 用法:
#   bash killswitch.sh                      # 直接处置（默认）
#   bash killswitch.sh --dry-run            # 只报告不动手
#   bash killswitch.sh --protect nginx,java # 额外保护业务进程（逗号分隔）
#
# 设计前提：服务器正在对外发包，SSH 随时可能断。
#   - 全程离线，不下载任何东西
#   - 冻结持久化在最前面（防止清理过程中被拉起）
#   - 先 SIGSTOP 挂起再清理，对付双进程互相拉起
#   - 绝不杀 sshd / 自身进程链 / 真内核线程

set -o pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

DRY=0; PROTECT_EXTRA=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --protect) PROTECT_EXTRA="$2"; shift ;;
  esac
  shift
done

# 必须 root。非 root 会静默失败——杀不动别人的进程、读不到 /proc/PID/exe，
# 最后打印"未命中"，给出机器干净的假象。这是应急场景最危险的错误，直接拦。
if [ "$(id -u)" != "0" ]; then
  if [ "$DRY" = "1" ]; then
    echo "! 非 root 演练：识别结果会严重不全（读不到其他用户的进程），仅供看流程"
  else
    echo "✗ 必须以 root 运行，否则会漏杀并误报干净。用 sudo bash $0"
    exit 1
  fi
fi

TS=$(date +%Y%m%d_%H%M%S)
EVID="/root/ir_$TS"
mkdir -p "$EVID" 2>/dev/null || { EVID="/tmp/ir_$TS"; mkdir -p "$EVID"; }
LOG="$EVID/killswitch.log"
exec > >(tee "$LOG") 2>&1

say() { echo "[$(date +%H:%M:%S)] $*"; }
act() { [ "$DRY" = 1 ] && echo "    [dry-run] $*" || eval "$*"; }

say "止损开始  主机=$(hostname)  证据目录=$EVID  模式=$([ $DRY = 1 ] && echo 演练 || echo 实处置)"

# ============================================================
# 阶段 0：建立保护名单（先做，后面所有操作都受它约束）
# ============================================================
PROTECTED_PIDS=" 1 "

# 自身进程链：从当前 PID 一路上溯到 1，全部保护
p=$$
while [ -n "$p" ] && [ "$p" != "0" ] && [ "$p" != "1" ]; do
  PROTECTED_PIDS="$PROTECTED_PIDS $p "
  p=$(awk '{print $4}' "/proc/$p/stat" 2>/dev/null)
done

# sshd 及其所有后代：杀了就断连
for s in $(pgrep -x sshd 2>/dev/null); do
  PROTECTED_PIDS="$PROTECTED_PIDS $s "
  for c in $(pgrep -P "$s" 2>/dev/null); do PROTECTED_PIDS="$PROTECTED_PIDS $c "; done
done

# kvm/qemu 是虚拟化宿主机(PVE/libvirt)上的客户机进程——VM 内挖矿会表现为宿主机上
# CPU 跑满的 kvm 进程，挂起它等于整台 VM 卡死，永远不碰；VM 内的事进 VM 里处理
PROTECT_NAMES="sshd systemd init dbus-daemon kvm qemu-system-x86 qemu-kvm"
[ -n "$PROTECT_EXTRA" ] && PROTECT_NAMES="$PROTECT_NAMES $(echo "$PROTECT_EXTRA" | tr ',' ' ')"

is_protected() {
  case "$PROTECTED_PIDS" in *" $1 "*) return 0 ;; esac
  local n; n=$(cat "/proc/$1/comm" 2>/dev/null)
  for x in $PROTECT_NAMES; do [ "$n" = "$x" ] && return 0; done
  return 1
}

say "保护名单就绪：sshd 会话链 + 自身进程链 + [$PROTECT_NAMES]"

# ============================================================
# 阶段 1：冻结持久化（最先做，1 秒内完成，防止边清边复活）
# ============================================================
say "阶段1 冻结定时任务"
cp -a /var/spool/cron "$EVID/cron.bak" 2>/dev/null
cp -a /etc/crontab /etc/cron.d /var/spool/at "$EVID/" 2>/dev/null
act "chmod 000 /var/spool/cron /var/spool/cron/crontabs /etc/cron.d 2>/dev/null"
act "systemctl stop crond cron atd 2>/dev/null"

# at 一次性任务：常被用来"几分钟后重新拉起被杀的进程"，只停 atd 不够
if atq 2>/dev/null | grep -q .; then
  say "  发现 at 队列任务（常用于延时复活），已备份并清空："
  atq 2>/dev/null
  act "atq 2>/dev/null | awk '{print \$1}' | xargs -r atrm 2>/dev/null"
fi

# docker 自动重启策略：容器进程杀了会被 docker 自动拉起
if command -v docker >/dev/null 2>&1; then
  docker ps -q 2>/dev/null | while read -r c; do
    pol=$(docker inspect "$c" --format '{{.HostConfig.RestartPolicy.Name}}' 2>/dev/null)
    case "$pol" in
      always|unless-stopped)
        say "  ! 容器 $(docker inspect "$c" --format '{{.Name}}' 2>/dev/null) 策略=$pol —— 若恶意进程在容器内，杀了会被自动拉起" ;;
    esac
  done
fi

# ============================================================
# 特征库加载
# ============================================================
FEED="$(dirname "$0")/../feeds/malware.txt"
[ -f "$FEED" ] || FEED="$(dirname "$0")/feeds/malware.txt"
BAD_NAMES=""; BAD_PATHS=""; BAD_PORTS=""; SOFT_PORTS=""; BAD_DOMAINS=""; MARKERS=""
if [ -f "$FEED" ]; then
  BAD_NAMES=$(grep '^name:'   "$FEED" | cut -d: -f2-)
  BAD_PATHS=$(grep '^path:'   "$FEED" | cut -d: -f2-)
  BAD_PORTS=$(grep '^port:'   "$FEED" | cut -d: -f2-)
  SOFT_PORTS=$(grep '^softport:' "$FEED" | cut -d: -f2-)
  BAD_DOMAINS=$(grep '^domain:' "$FEED" | cut -d: -f2-)
  MARKERS=$(  grep '^marker:' "$FEED" | cut -d: -f2-)
  say "特征库已加载：$(echo "$BAD_NAMES $BAD_PATHS" | wc -w) 条进程/路径特征"
else
  say "! 特征库缺失，仅靠行为判据运行（能力下降）"
fi

# ============================================================
# 阶段 1.5：信任评估 —— 这台机器的命令输出还能不能信？
# ============================================================
say "阶段1.5 评估系统命令可信度"
TRUST=1

if [ -s /etc/ld.so.preload ]; then
  TRUST=0
  say "  ✗ /etc/ld.so.preload 非空 —— 用户态 rootkit，库函数被劫持"
  cat /etc/ld.so.preload
fi

# 盖茨木马会替换 ps/netstat/lsof/ss，并把干净的原始命令备份在这个目录
if [ -d /usr/bin/dpkgd ]; then
  TRUST=0
  say "  ✗ /usr/bin/dpkgd/ 存在 —— 盖茨木马(BillGates)铁证，ps/netstat/lsof/ss 已被替换"
  say "    该目录内是干净的原始命令备份，修复："
  for c in ps netstat lsof ss; do
    [ -f "/usr/bin/dpkgd/$c" ] && say "      cp -f /usr/bin/dpkgd/$c \$(which $c)"
  done
fi

# 非发行版内核目录的模块 = 疑似 rootkit
for m in $(lsmod 2>/dev/null | tail -n +2 | awk '{print $1}'); do
  modinfo "$m" 2>/dev/null | grep -q "^filename:.*/kernel/" || {
    TRUST=0
    say "  ✗ 可疑内核模块：$m —— 内核级 rootkit，进程/连接可被彻底隐藏"
  }
done

if [ "$TRUST" = 0 ]; then
  say "  ⚠ 判定：本机命令输出不可信。"
  say "    本脚本全程直读 /proc，不依赖 ps/netstat，识别结果仍有效；"
  say "    但你手工执行的 ps/top/netstat 会看到被美化过的假象。"
  say "    存在内核级 rootkit 时，连 /proc 也可能被过滤 → 建议挂盘离线分析或重装。"
else
  say "  ✓ 未发现命令劫持迹象，ps/netstat 输出可信"
fi

# 标志文件扫描：存在即定性，不杀进程
for mk in $MARKERS; do
  [ -e "$mk" ] && { say "  ⚠ 命中标志物：$mk"; echo "$mk" >> "$EVID/markers.txt"; }
done

# ============================================================
# 阶段 2：识别（三级判据，全程直读 /proc，绕开可能被劫持的命令）
# ============================================================

say "阶段2 识别可疑进程"
HITS=""; SUSPECT=""

for d in /proc/[0-9]*; do
  pid=${d#/proc/}
  [ -d "$d" ] || continue
  is_protected "$pid" && continue

  exe=$(readlink "$d/exe" 2>/dev/null)
  comm=$(cat "$d/comm" 2>/dev/null)
  cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)
  reason=""

  # 真内核线程：无 exe 且 cmdline 为空 —— 一律跳过
  [ -z "$exe" ] && [ -z "$cmd" ] && continue

  # L1 命中特征库
  for n in $BAD_NAMES; do
    case "$comm" in *"$n"*) reason="命中恶意进程名[$n]" ;; esac
    [ -n "$reason" ] && break
  done
  if [ -z "$reason" ]; then
    for pth in $BAD_PATHS; do
      case "$exe" in "$pth"*) reason="命中恶意路径[$pth]"; break ;; esac
    done
  fi

  # L2 强可疑行为
  if [ -z "$reason" ]; then
    case "$exe" in
      *"(deleted)"*) reason="可执行文件已被删除（木马删自身）" ;;
    esac
  fi
  # 伪装成内核线程但有 exe —— 强恶意信号
  if [ -z "$reason" ]; then
    case "$comm" in
      "["*"]"|kworker*|kthreadd*|ksoftirqd*|migration*)
        [ -n "$exe" ] && reason="伪装内核线程但有实体文件 → $exe" ;;
    esac
  fi
  # 落马目录里跑起来的进程
  if [ -z "$reason" ]; then
    case "$exe" in
      /tmp/*|/var/tmp/*|/dev/shm/*|/run/user/*) reason="从临时目录执行 → $exe" ;;
    esac
  fi
  # 命令行参数里带矿池域名 —— xmrig 惯用 -o pool.xxx:3333，铁证级
  if [ -z "$reason" ]; then
    for dm in $BAD_DOMAINS; do
      case "$cmd" in *"$dm"*) reason="命令行含矿池/恶意域名[$dm]"; break ;; esac
    done
  fi

  if [ -n "$reason" ]; then
    cpu=$(ps -o %cpu= -p "$pid" 2>/dev/null | tr -d ' ')
    say "  ⚠ PID=$pid  $comm  CPU=${cpu}%  —— $reason"
    echo "PID=$pid COMM=$comm EXE=$exe CMD=$cmd REASON=$reason" >> "$EVID/hits.txt"
    HITS="$HITS $pid"
  fi
done

# 连接到已知恶意端口的进程
# 直读 /proc/net/tcp 而非 ss —— XorDDoS 等家族会劫持 ss/netstat 抹掉自己的连接
if [ -n "$BAD_PORTS$SOFT_PORTS" ]; then
  # 先建 socket inode → PID 的映射
  INODE_MAP="$EVID/.inode_map"
  : > "$INODE_MAP"
  for d in /proc/[0-9]*/fd; do
    pid=${d#/proc/}; pid=${pid%/fd}
    for fd in "$d"/*; do
      lnk=$(readlink "$fd" 2>/dev/null)
      case "$lnk" in
        socket:\[*\]) ino=${lnk#socket:[}; ino=${ino%]}; echo "$ino $pid" >> "$INODE_MAP" ;;
      esac
    done
  done 2>/dev/null

  for net in /proc/net/tcp /proc/net/tcp6; do
    [ -f "$net" ] || continue
    tail -n +2 "$net" 2>/dev/null | while read -r _ _ rem st _ _ _ _ _ ino _; do
      # rem 格式为 十六进制IP:十六进制端口
      hexport=${rem##*:}
      dport=$((16#$hexport))
      [ "$st" = "01" ] || continue   # 只看已建立的连接
      for prt in $BAD_PORTS; do
        [ "$dport" = "$prt" ] || continue
        pid=$(awk -v i="$ino" '$1==i {print $2; exit}' "$INODE_MAP")
        [ -n "$pid" ] && echo "$pid $prt hard" >> "$EVID/.porthits"
      done
      for prt in $SOFT_PORTS; do
        [ "$dport" = "$prt" ] || continue
        pid=$(awk -v i="$ino" '$1==i {print $2; exit}' "$INODE_MAP")
        [ -n "$pid" ] && echo "$pid $prt soft" >> "$EVID/.porthits"
      done
    done
  done

  if [ -f "$EVID/.porthits" ]; then
    while read -r pid prt kind; do
      is_protected "$pid" && continue
      case " $HITS " in *" $pid "*) continue ;; esac
      nm=$(cat "/proc/$pid/comm" 2>/dev/null)
      if [ "$kind" = soft ]; then
        # 合法服务端口被恶意复用：只报告，不击杀（误杀业务的代价更高）
        say "  ! PID=$pid $nm 连接 $prt —— 该端口既是正常服务也被木马复用，需人工确认，不自动杀"
        echo "PID=$pid PORT=$prt 需人工确认" >> "$EVID/soft_hits.txt"
      else
        say "  ⚠ PID=$pid $nm —— 连接已知恶意端口 $prt"
        echo "PID=$pid REASON=连恶意端口$prt" >> "$EVID/hits.txt"
        HITS="$HITS $pid"
      fi
    done < <(sort -u "$EVID/.porthits")
    rm -f "$EVID/.porthits" "$INODE_MAP"
  fi
fi

# 自愈型守护：用 inotifywait 盯着自己的文件，删了立刻从备份恢复
for pid in $(pgrep -f inotifywait 2>/dev/null); do
  is_protected "$pid" && continue
  case " $HITS " in *" $pid "*) continue ;; esac
  say "  ⚠ PID=$pid inotifywait —— 文件自愈守护，不连它一起杀则删了会立刻恢复"
  echo "PID=$pid REASON=inotify自愈守护" >> "$EVID/hits.txt"
  HITS="$HITS $pid"
done

# 被 LD_PRELOAD 注入的进程：只报告不杀（这些往往是被感染的正常业务进程）
for d in /proc/[0-9]*; do
  [ -r "$d/environ" ] || continue
  pid=${d#/proc/}
  pre=$(tr '\0' '\n' < "$d/environ" 2>/dev/null | grep '^LD_PRELOAD=')
  [ -n "$pre" ] && {
    say "  ! PID=$pid $(cat "$d/comm" 2>/dev/null) 带 $pre —— 疑似被注入，不自动杀（可能是业务进程），需人工确认"
    echo "PID=$pid $pre 疑似注入" >> "$EVID/preload_injected.txt"
  }
done

# 落地配置文件里的矿池域名 —— 进程可能已被杀或还没启动，但配置文件还在
if [ -n "$BAD_DOMAINS" ]; then
  DOM_PAT=$(echo $BAD_DOMAINS | tr ' ' '|')

  # /etc/hosts 被写入矿池域名：木马为规避 DNS 拦截而自带解析
  hosts_hit=$(grep -Ei "$DOM_PAT" /etc/hosts 2>/dev/null)
  [ -n "$hosts_hit" ] && {
    say "  ⚠ /etc/hosts 含矿池域名（木马自带解析规避 DNS 拦截）"
    echo "$hosts_hit"
    echo "$hosts_hit" >> "$EVID/hosts_hit.txt"
  }

  for dir in /tmp /var/tmp /dev/shm /root /etc /usr/local/etc /home; do
    [ -d "$dir" ] || continue
    find "$dir" -maxdepth 3 -type f -size -1M \
         \( -name "*.json" -o -name "*.conf" -o -name "*.cfg" -o -name "*.sh" -o -name "*.xml" \) \
         2>/dev/null | while read -r f; do
      m=$(grep -oEi "$DOM_PAT" "$f" 2>/dev/null | head -1)
      [ -n "$m" ] && {
        say "  ⚠ 配置文件含矿池域名 [$m] → $f"
        echo "$f : $m" >> "$EVID/domain_in_config.txt"
      }
    done
  done
fi

if [ -z "$HITS" ]; then
  say "未命中任何已知特征。转人工：附上 $EVID 和 triage.sh 输出交给 Claude 分析。"
fi

# ============================================================
# 阶段 3：SIGSTOP 挂起（不是 kill —— 防止守护进程察觉后拉起新的）
# ============================================================
if [ -n "$HITS" ]; then
  say "阶段3 一次性挂起全部可疑进程"
  # 必须一条命令同时冻住：逐个挂起会留出时间差，守护进程会在这个空档拉起新的
  act "kill -STOP $HITS 2>/dev/null"

  # 验证是否真冻住（STAT 列为 T）
  for pid in $HITS; do
    st=$(awk '{print $3}' "/proc/$pid/stat" 2>/dev/null)
    case "$st" in
      T) ;;
      "") say "  ! PID=$pid 已消失（可能自行退出或被同伙杀掉）" ;;
      *)  say "  ! PID=${pid} 未能挂起（状态=${st}），可能受内核模块保护 → 需人工处理" ;;
    esac
  done

  # 冻住后再扫一遍：看有没有新进程补位（说明还有没抓到的守护进程）
  sleep 2
  for d in /proc/[0-9]*; do
    pid=${d#/proc/}
    case " $HITS $PROTECTED_PIDS " in *" $pid "*) continue ;; esac
    exe=$(readlink "$d/exe" 2>/dev/null)
    case "$exe" in
      *"(deleted)"*|/tmp/*|/var/tmp/*|/dev/shm/*)
        say "  ⚠ 挂起后出现新进程 PID=$pid $(cat "$d/comm" 2>/dev/null) —— 存在未捕获的守护进程"
        act "kill -STOP $pid 2>/dev/null"
        HITS="$HITS $pid" ;;
    esac
  done
fi

# ============================================================
# 阶段 4：取证快照（进程已冻住，可以从容采集）
# ============================================================
say "阶段4 取证快照 → $EVID"
ps auxf                  > "$EVID/ps.txt" 2>/dev/null
ss -tunap                > "$EVID/net.txt" 2>/dev/null
lsmod                    > "$EVID/lsmod.txt" 2>/dev/null
last -30                 > "$EVID/last.txt" 2>/dev/null
cat /etc/ld.so.preload   > "$EVID/ld_preload.txt" 2>/dev/null
for pid in $HITS; do
  # 从 /proc 复制而非从磁盘路径：木马常删掉自己的磁盘文件，此处是唯一完整副本
  cp "/proc/$pid/exe"  "$EVID/sample_${pid}"   2>/dev/null
  cp "/proc/$pid/maps" "$EVID/maps_${pid}.txt" 2>/dev/null
  ls -la "/proc/$pid/fd" > "$EVID/fd_${pid}.txt" 2>/dev/null
  tr '\0' '\n' < "/proc/$pid/environ" > "$EVID/env_${pid}.txt" 2>/dev/null
done
sha256sum "$EVID"/sample_* > "$EVID/hashes.txt" 2>/dev/null
say "  已保存样本文件+内存映射+打开的文件句柄；哈希拿去查是哪个家族"

# 外连 IP 清单：直读 /proc/net/tcp，绕开可能被劫持的 ss/netstat
# 用途：交云安全组封禁出向 + 交 cve-intel 查是不是已知矿池/C2
{
  for net in /proc/net/tcp /proc/net/tcp6; do
    [ -f "$net" ] || continue
    tail -n +2 "$net" 2>/dev/null | awk '$4=="01"{print $3}' | while read -r rem; do
      hip=${rem%:*}; hpt=${rem#*:}
      port=$((16#$hpt))
      if [ ${#hip} = 8 ]; then   # IPv4：小端十六进制，四段反序
        printf '%d.%d.%d.%d:%d\n' 0x${hip:6:2} 0x${hip:4:2} 0x${hip:2:2} 0x${hip:0:2} "$port"
      fi
    done
  done
} 2>/dev/null | grep -vE '^(127\.|0\.0\.0\.0)' | sort -u > "$EVID/outbound_ips.txt"
NOUT=$(grep -c . "$EVID/outbound_ips.txt" 2>/dev/null || echo 0)
say "  外连目标 $NOUT 个 → $EVID/outbound_ips.txt（交云安全组封出向 + cve-intel 查信誉）"

# ============================================================
# 阶段 5：清持久化（进程还冻着，清完它也拉不起来）
# ============================================================
say "阶段5 清持久化"
for f in /var/spool/cron/* /var/spool/cron/crontabs/* /etc/cron.d/*; do
  [ -f "$f" ] || continue
  if grep -qE "curl|wget|base64|\.sh\s*\||/tmp/|/dev/shm" "$f" 2>/dev/null; then
    say "  可疑定时任务 → $f （已备份）"
    grep -nE "curl|wget|base64|/tmp/|/dev/shm" "$f"
    act "chattr -i '$f' 2>/dev/null; : > '$f'"
  fi
done

# 冷门持久化位置：只报告不自动清（误删会影响系统），但必须让人看见
say "  扫描冷门持久化位置"
for f in /etc/rc.local /etc/rc.d/rc.local /root/.bashrc /root/.bash_profile \
         /root/.bash_logout /etc/profile /etc/profile.d/*.sh /etc/bashrc /etc/bash.bashrc; do
  [ -f "$f" ] && grep -lE "curl|wget|base64 -d|/dev/tcp/|/tmp/|/dev/shm|nc -e" "$f" 2>/dev/null \
    && { say "    ! 可疑内容 → $f"; grep -nE "curl|wget|base64 -d|/dev/tcp/|/tmp/|/dev/shm|nc -e" "$f"; }
done

# 每次 SSH 登录都以 root 执行，极易被忽略
for f in /etc/update-motd.d/* /etc/ssh/sshrc /root/.ssh/rc; do
  [ -f "$f" ] && grep -lE "curl|wget|base64|/tmp/" "$f" 2>/dev/null && say "    ! 登录触发脚本可疑 → $f"
done

# udev 规则：设备事件触发，无需重启即生效
grep -rlE "RUN\+?=|PROGRAM=" /etc/udev/rules.d/ 2>/dev/null | while read -r f; do
  grep -qE "/tmp/|/dev/shm|curl|wget|\.sh" "$f" 2>/dev/null && say "    ! udev 规则可疑 → $f"
done

# systemd generator：开机极早期执行，常规巡检不覆盖
for dir in /etc/systemd/system-generators /run/systemd/system-generators; do
  [ -d "$dir" ] && ls -A "$dir" 2>/dev/null | grep -q . && say "    ! 存在 systemd generator（极隐蔽）→ $dir"
done

# 近期新增的 systemd 服务
find /etc/systemd/system -name "*.service" -mtime -7 2>/dev/null | while read -r f; do
  say "    ! 近 7 天新增服务 → $f"
  grep -E "^ExecStart" "$f" 2>/dev/null
done

# 陌生 SSH 公钥
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] && [ -s "$f" ] && { say "    ! 核对公钥（改密码清不掉后门）→ $f"; cat "$f" | cut -c1-80; }
done

# UID 0 的非 root 账号
awk -F: '$3==0 && $1!="root" {print "    ! UID0 后门账号 → "$1}' /etc/passwd

if [ -s /etc/ld.so.preload ]; then
  say "  ⚠ ld.so.preload 非空 —— 存在 rootkit，本脚本此前所有输出都可能被伪造"
  cat /etc/ld.so.preload
  act "chattr -i /etc/ld.so.preload 2>/dev/null; : > /etc/ld.so.preload"
  say "  ⚠ 强烈建议：此机重装。rootkit 无法验证清干净。"
fi

# ============================================================
# 阶段 6：真杀 + 删文件
# ============================================================
if [ -n "$HITS" ]; then
  say "阶段6 终止进程并清除文件"
  for pid in $HITS; do
    exe=$(readlink -f "/proc/$pid/exe" 2>/dev/null)
    act "kill -9 $pid 2>/dev/null"
    if [ -n "$exe" ] && [ -f "$exe" ]; then
      case "$exe" in
        /bin/*|/sbin/*|/usr/bin/*|/usr/sbin/*|/lib/*)
          say "  ! $exe 位于系统目录，不自动删（可能是被替换的系统命令，需人工确认）" ;;
        *)
          act "chattr -i '$exe' 2>/dev/null; rm -f '$exe'"
          say "  已删除 $exe" ;;
      esac
    fi
  done
  sleep 2
  for pid in $HITS; do
    [ -d "/proc/$pid" ] && say "  ! PID=$pid 仍存活，可能被内核模块保护 → 需人工处理"
  done
fi

# ============================================================
# 阶段 7：解冻 cron + 报告
# ============================================================
say "阶段7 恢复 cron 权限"
act "chmod 755 /var/spool/cron /etc/cron.d 2>/dev/null"
act "chmod 700 /var/spool/cron/crontabs 2>/dev/null"

echo
say "===== 止损完成 ====="
say "证据目录：$EVID （查入口点要用，别删）"
say "已处置进程：$(echo $HITS | wc -w) 个"
echo
say "下一步（现在做，不然会再中）："
say "  1. 改所有密码、换 SSH 密钥、检查 authorized_keys 有没有陌生公钥"
say "  2. 找入口：SSH 爆破 / Redis 未授权 / 应用漏洞 —— 不找到就会复发"
say "  3. 同网段其他机器一并检查，通常是批量沦陷"
say "  4. 把 $EVID 交给 Claude 分析定性"
