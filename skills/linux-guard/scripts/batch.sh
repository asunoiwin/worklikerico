#!/bin/bash
# batch.sh —— 把只读检查脚本批量推到多台机器跑，结果收回本地汇总
#
# 用法:
#   bash batch.sh hosts.txt                         # 默认批量体检 checkup.sh
#   bash batch.sh hosts.txt killswitch.sh --dry-run   # 同目录脚本，批量只读排查
#   bash batch.sh hosts.txt triage.sh
#
# hosts.txt：每行一个 root@ip 或 user@ip（# 开头的行跳过）
#
# 安全边界（有意的限制）：
#   · 只分发【只读】脚本 —— checkup / triage / killswitch --dry-run
#   · 绝不批量执行 killswitch（真杀）或 harden --apply
#     一次误判会同时打到一批生产机，处置必须逐台人工确认。
#   本脚本会拒绝分发带 --apply 的命令。

HOSTS="$1"; shift
SCRIPT="${1:-$(dirname "$0")/checkup.sh}"
[ $# -gt 0 ] && shift
ARGS="$*"
PAR="${PAR:-5}"   # 并发数，PAR=10 bash batch.sh ... 可调

[ -f "$HOSTS" ]  || { echo "用法: bash batch.sh hosts.txt [脚本] [参数]"; exit 1; }
[ -f "$SCRIPT" ] || SCRIPT="$(dirname "$0")/$SCRIPT"
[ -f "$SCRIPT" ] || { echo "找不到脚本: $SCRIPT"; exit 1; }

# 安全闸：批量只准跑只读
case "$ARGS" in
  *--apply*) echo "✗ 拒绝批量 --apply。批量只做只读，处置逐台人工确认。"; exit 1 ;;
esac
# killswitch 默认就动手杀，批量分发它必须显式 --dry-run，否则等于批量真杀
case "$(basename "$SCRIPT")" in
  killswitch.sh)
    case "$ARGS" in
      *--dry-run*) ;;
      *) echo "✗ 批量跑 killswitch 必须加 --dry-run。真杀请逐台人工执行，不批量。"; exit 1 ;;
    esac ;;
esac

OUTDIR="./batch_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTDIR"

echo "批量分发: $(basename "$SCRIPT") $ARGS"
echo "目标: $(grep -vcE '^\s*#|^\s*$' "$HOSTS") 台   并发: $PAR   结果目录: $OUTDIR"
echo

run_one() {
  host="$1"; script="$2"; args="$3"; out="$4"
  # 把脚本内容通过 stdin 喂过去执行，免 scp；参数用环境变量传
  if ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
         -o ServerAliveInterval=5 -C "$host" "bash -s -- $args" < "$script" \
         > "$out/${host//[^a-zA-Z0-9._-]/_}.txt" 2>&1; then
    echo "  ✓ $host"
  else
    echo "  ✗ $host（连接失败或脚本报错，看 $out/${host//[^a-zA-Z0-9._-]/_}.txt）"
  fi
}
export -f run_one

grep -vE '^\s*#|^\s*$' "$HOSTS" | \
  xargs -P "$PAR" -I{} bash -c 'run_one "$@"' _ {} "$SCRIPT" "$ARGS" "$OUTDIR"

echo
echo "════ 汇总（按高危标记数排序）════"
for f in "$OUTDIR"/*.txt; do
  [ -f "$f" ] || continue
  h=$(basename "$f" .txt)
  hi=$(grep -c "高危\|✗ \[高危\]\|命中恶意\|命中木马" "$f" 2>/dev/null)
  printf "%-30s 高危/命中 %s 处\n" "$h" "$hi"
done | sort -k3 -rn

echo
echo "全部结果在 $OUTDIR/   高危数 >0 的机器优先看。"
echo "发现疑似入侵的机器：单独登录跑 killswitch.sh（真杀），不要批量。"
