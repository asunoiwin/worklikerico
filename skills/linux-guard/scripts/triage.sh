#!/bin/bash
# 离线只读现场采集 —— 不修改系统任何状态，可在生产机直接运行
# 用法: bash triage.sh [输出文件]   默认输出到 /tmp/triage_主机名_时间.txt

OUT="${1:-/tmp/triage_$(hostname)_$(date +%Y%m%d_%H%M%S).txt}"
exec > >(tee "$OUT") 2>&1

sec() { echo; echo "===== $1 ====="; }

echo "采集时间: $(date)  主机: $(hostname)  内核: $(uname -r)"

sec "CPU 占用 TOP10"
ps aux --sort=-%cpu 2>/dev/null | head -11

sec "对外连接（挖矿看是否连 3333/4444/5555/7777/14444/45700）"
ss -tunap 2>/dev/null | grep -E "ESTAB|SYN-SENT" | head -40

sec "监听端口"
ss -tlnp 2>/dev/null

sec "可执行文件已被删除的进程（强恶意信号）"
for p in /proc/[0-9]*; do
  exe=$(readlink "$p/exe" 2>/dev/null)
  case "$exe" in *"(deleted)"*) echo "PID ${p#/proc/}: $exe  CMD: $(tr '\0' ' ' < "$p/cmdline" 2>/dev/null)";; esac
done

sec "ld.so.preload（非空说明有 rootkit，以上所有输出均不可信）"
cat /etc/ld.so.preload 2>/dev/null || echo "(不存在，正常)"

sec "非常规内核模块"
lsmod 2>/dev/null | tail -n +2 | awk '{print $1}' | while read -r m; do
  modinfo "$m" 2>/dev/null | grep -q "^filename:.*/kernel/" || echo "可疑: $m"
done

sec "SSH 授权公钥（认不出的即后门）"
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] && { echo "--- $f"; cat "$f"; }
done

sec "定时任务"
for f in /var/spool/cron/* /var/spool/cron/crontabs/* /etc/crontab /etc/cron.d/*; do
  [ -f "$f" ] && { echo "--- $f"; grep -v "^#" "$f" | grep -v "^$"; }
done

sec "systemd 定时器"
systemctl list-timers --all --no-pager 2>/dev/null | head -20

sec "近 7 天新增/修改的 systemd 服务"
find /etc/systemd /usr/lib/systemd -name "*.service" -mtime -7 2>/dev/null

sec "UID 0 账号（root 之外的都是后门）"
awk -F: '$3==0 {print $1}' /etc/passwd

sec "可登录账号"
grep -vE "nologin|/bin/false" /etc/passwd

sec "启动项与 shell 配置"
for f in /etc/rc.local /root/.bashrc /root/.bash_profile /etc/profile; do
  [ -f "$f" ] && { echo "--- $f"; grep -nE "curl|wget|base64|/dev/tcp|python -c|bash -i" "$f"; }
done

sec "近 3 天变动的可执行文件（常见落马目录）"
find /tmp /var/tmp /dev/shm /usr/bin /usr/sbin -type f -mtime -3 2>/dev/null | head -40

sec "登录成功记录"
last -20 2>/dev/null

sec "SSH 爆破迹象"
grep -h "Failed password" /var/log/secure /var/log/auth.log 2>/dev/null | \
  awk '{for(i=1;i<=NF;i++) if($i=="from") print $(i+1)}' | sort | uniq -c | sort -rn | head -10

sec "SSH 成功登录来源"
grep -h "Accepted" /var/log/secure /var/log/auth.log 2>/dev/null | tail -20

echo
echo "采集完成，报告: $OUT"
