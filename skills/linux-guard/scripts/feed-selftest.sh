#!/bin/bash
# feed-selftest.sh —— 特征库误伤回归测试
# 复刻 killswitch.sh 的进程名子串匹配逻辑：确认 name: 条目
#   ① 不撞任何真实系统进程名（撞了=生产事故，杀正常进程）
#   ② 已知木马名全部检得出
# 用法：bash feed-selftest.sh [特征库路径]   默认 ../feeds/malware.txt
# 退出码 0=通过，1=有误伤或漏检。update-feed.sh 的合并门调它，不过不落盘。
# 注意：必须用 bash 跑，zsh 分词不同会假通过。

FEED="${1:-$(dirname "$0")/../feeds/malware.txt}"
[ -f "$FEED" ] || { echo "找不到特征库: $FEED"; exit 1; }
BAD_NAMES=$(grep '^name:' "$FEED" | cut -d: -f2-)

hit() {
  local comm="$1" n
  for n in $BAD_NAMES; do
    case "$comm" in *"$n"*) echo "$n"; return 0 ;; esac
  done
  return 1
}

# 真实系统进程/内核线程 + 情报源易混入的通用组件名，全都不许命中
REAL="systemd kthreadd kswapd0 ksoftirqd/0 kworker/0:1 kauditd rcu_sched migration/0 \
watchdog/0 sshd bash sh dash httpd nginx mysqld redis-server postgres java python3 \
node dockerd containerd kvm qemu-system-x86 crond rsyslogd agetty dbus-daemon \
NetworkManager chronyd ntpd auditd irqbalance polkitd top ps mm_percpu_wq \
xfsaild/dm-0 jbd2/sda1-8 Update cache Opera miner linux vmtoolsd"

# 已知木马名，必须全检出
BADP="kdevtmpfsi kinsing kswapd01 kthreadadd ksoftirqds redtail perfctl wizlmsh \
sysrv kthreaddi watchdogs qW3xT 2t3ik hezb pwnrig xmrig Mozi.a dropbpb bpb.mips \
klibsystem4 oanacroner .diicot hadooken koske nanominer.koske mdrfckr blitz"

fp=0; fn=0
echo "── 真实进程/通用词（应零命中）──"
for p in $REAL; do
  h=$(hit "$p") && { echo "  ✗ 误伤: $p ← 特征[$h]"; fp=$((fp+1)); }
done
[ $fp = 0 ] && echo "  全部通过（$(echo $REAL | wc -w | tr -d ' ') 个）"

echo "── 木马名（应全命中）──"
for p in $BADP; do
  hit "$p" >/dev/null || { echo "  ✗ 漏检: $p"; fn=$((fn+1)); }
done
[ $fn = 0 ] && echo "  全部检出（$(echo $BADP | wc -w | tr -d ' ') 个）"

echo "── 特征库统计 ──"
for t in name path port softport domain marker; do
  printf "  %-9s %s\n" "$t:" "$(grep -c "^$t:" "$FEED")"
done

if [ $fp = 0 ] && [ $fn = 0 ]; then echo "RESULT: PASS"; exit 0
else echo "RESULT: FAIL (误伤 $fp / 漏检 $fn)"; exit 1; fi
