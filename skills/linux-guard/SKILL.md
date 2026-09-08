---
name: linux-guard
description: Linux 服务器安全一体化 —— 两种模式：①应急止损（机器正在对外发包/挖矿/被云厂商告警，先杀进程、清病毒文件、堵后门）；②日常体检（没出事时查暴露面、SSH 配置、账号后门、木马残留、补丁状态，出带优先级的整改清单）。特征库覆盖挖矿与 DDoS 家族。应急触发词：服务器被入侵 / 对外发包 / 挖矿 / 中马 / 肉鸡 / 异常流量 / CPU跑满 / 被云厂商告警 / 被封端口 / 应急响应 / 中病毒 / 有后门。体检触发词：安全体检 / 安全检查 / 巡检 / 加固 / 基线检查 / 漏洞扫描 / Trivy / 服务器安全吗 / 有没有风险 / 等保自查。
---

# Linux 服务器安全（应急止损 + 日常体检）

## 先定模式（第一件事，不能跳）

| 问一个问题 | 答案 | 走哪个模式 |
|---|---|---|
| 机器**现在**有没有异常？（发包 / CPU 跑满 / 云厂商告警 / 发现可疑进程） | 有 | **模式 A：应急止损** —— 默认动手杀 |
| 同上 | 没有，只是想检查 / 加固 / 定期巡检 | **模式 B：日常体检** —— 纯只读 |

**两个模式的默认行为相反，这是有意设计，不许改：**

- 模式 A 的 `killswitch.sh` **默认直接杀**（杀错重启服务即可，不杀会被封号）
- 模式 B 的 `checkup.sh` **纯只读**；模式 A 里的 `harden.sh` 也**默认只出建议**（改 SSH 错了会锁死自己）
- `batch.sh` 批量分发**只准只读**，真杀永远逐台人工
- 拿不准算不算"出事" → 先跑模式 B 或 `killswitch.sh --dry-run`，只读永远安全

---

# 模式 A：应急止损

## 头等大事：不要浪费时间问

**发包每多一分钟，被云厂商封号的风险就多一分。** 判断权交给特征库和行为判据，不交给对话。

- **命中特征库 / 命中强可疑行为 → 直接杀，不问。** 杀错业务进程重启服务即可恢复；不杀导致账号被封，损失大得多。
- **只有四件事需要问用户**：整机断网、重装系统、删除系统目录下的文件、修改 SSH 配置。
- 不要问"要不要我执行"。直接执行，执行完报告干了什么。

## 三个阶段，缺一不可

| 阶段 | 脚本 | 做什么 | 不做的后果 |
|---|---|---|---|
| **止血** | `killswitch.sh` | 冻持久化 → 识别 → 挂起 → 取证 → 杀 → 删文件 | 持续发包被封号 |
| **堵口** | `harden.sh` | 清 SSH 公钥后门、账号后门、PAM 后门、封暴露服务 | **必然复发** |
| **验证** | 重跑 + 重启复查 | 确认真的清干净了 | 以为清完了其实还在 |

**只做第一步是最常见的错误。** 杀干净了、CPU 降下来了，三天后又中——因为入口没堵，或者后门没清。

## 第 0 步：先解决"连不上"

发包时带宽被打满，SSH 握手最容易丢包：

```bash
ssh -4 -C -o ConnectTimeout=5 -o ServerAliveInterval=5 -o ServerAliveCountMax=3 \
    -o TCPKeepAlive=yes -o IPQoS=throughput \
    -o ControlMaster=auto -o ControlPersist=10m root@目标IP
```

`ControlPersist` 是这里最值钱的一条——**成功握手一次后，后续命令不用再握手**。

连上后立刻切 mosh 抗丢包：`mosh --ssh="ssh -p 22" root@目标IP`

**完全连不上**：走云厂商控制台的 VNC / 串口登录，不经过业务网络。同时在云控制台安全组掐出向——木马有 root 能改机器里的 iptables，但改不了云控制台。

## 第 1 步：一键止损

```bash
bash killswitch.sh                      # 直接处置
bash killswitch.sh --dry-run            # 只报告不动手
bash killswitch.sh --protect nginx,java # 额外保护业务进程
```

零联网、零依赖（发包时下载工具那条路走不通）。流程：

1. **立保护名单** —— sshd 会话链 + 脚本自身进程链 + 真内核线程，一个不许杀
2. **冻结持久化** —— cron、at 队列（常用于延时复活）、检查 docker 自动重启策略
3. **信任评估** —— 查 `ld.so.preload`、`/usr/bin/dpkgd/`、可疑内核模块，判断 ps/netstat 输出还能不能信
4. **识别** —— 见下方判据表
5. **一次性全部挂起** —— 必须一条命令同时冻住；挂起后重扫，有新进程冒出说明还有漏网守护进程
6. **取证** —— 从 `/proc` 复制样本 + 内存映射 + 打开的句柄
7. **清持久化 → 真杀 → 删文件**

### 识别判据

| 判据 | 说明 |
|---|---|
| 特征库进程名/路径命中 | 见 `feeds/malware.txt` |
| **可执行文件已被删除** | 木马删自身，正常程序不会这样 |
| **伪装内核线程但有实体文件** | 真内核线程在 `/proc/PID/exe` 读不到文件，几乎不误伤 |
| 从 `/tmp`、`/dev/shm` 等临时目录执行 | |
| 命令行或配置文件含矿池域名 | xmrig 惯用 `-o pool.xxx:3333`，铁证级 |
| 连接已知恶意端口 | 直读 `/proc/net/tcp`，绕开可能被劫持的 `ss` |
| inotify 自愈守护 | 盯着自己的文件，删了立刻恢复 |

**被 LD_PRELOAD 注入的进程只报告不杀** —— 被注入的往往是正常业务进程。

## 第 2 步：清病毒文件

杀进程只是止血，文件不清会被重新拉起。killswitch 会自动删掉命中进程的可执行文件，这几类要额外处理：

**文件被锁死删不掉**
```bash
lsattr /path/to/file        # 第 5 位是 i 说明被锁
chattr -i /path/to/file && rm -f /path/to/file
```
连 `chattr` 本身都可能被替换，可疑时用静态编译的 busybox：
```bash
/tmp/busybox chattr -i /path/to/file
```

**隐藏文件与目录**（木马爱用点号开头、伪装成系统路径）
```bash
find /tmp /var/tmp /dev/shm -name ".*" -mtime -7 2>/dev/null
ls -la /tmp/.X11-unix /tmp/.X25-unix /dev/shm 2>/dev/null
```

**位于系统目录的不要自动删** —— 那可能是被替换的 `ps`/`netstat`，删了系统就残了。走 `harden.sh` 用包管理器重装恢复。

**关联文件**（清了主体还剩配置和脚本，重新拉起时照样能跑）
```bash
find / -xdev \( -name "config.json" -o -name "*.lock" -o -name "*.pid" \) -mtime -7 2>/dev/null | grep -vE "^/(proc|sys|var/lib)"
```

**内存马**：新版 Chalubo、Ballista 刻意不落盘，纯内存运行。磁盘上找不到文件是正常的——杀掉进程即清除，但重启后又出现说明入口还开着。

## 第 3 步：脚本搞不定的情况

| 现象 | 处置 |
|---|---|
| 杀完仍存活 / 挂不住 | 有内核模块保护，查 `lsmod` 里 `modinfo` 查不到的模块 |
| `ld.so.preload` 非空 | 用户态 rootkit，**ps/ls/netstat 全部不可信**，包括脚本自己打印的 |
| `/usr/bin/dpkgd/` 存在 | 盖茨木马，里面是干净的原始命令备份，可直接拷回 |
| 未命中任何特征 | 把证据目录交给 Claude 分析，别硬猜 |

**确认有内核级 rootkit 就别清了，重装。** 清不干净，也无法验证清干净了。

## 阶段二：堵口

```bash
bash harden.sh            # 只诊断 + 输出命令（默认）
bash harden.sh --apply    # 执行不会中断业务的那部分
```

**默认不动手，与 killswitch 相反。** 改 SSH 配置改错会导致再也连不上，而这类机器多半没有带外通道。

覆盖七类后门与入口：

1. **SSH 公钥后门** —— 改密码对它完全无效，不清等于门一直开着。脚本列出每个公钥并自动备份，由你逐个核对
2. **账号后门** —— UID 0 的非 root 账号、空密码账号、近期新建的家目录
3. **PAM 后门** —— 替换认证模块植入万能密码，常规扫描发现不了，用包管理器校验完整性
4. **被替换的系统命令** —— `rpm -V` / `dpkg -V` 校验，给出重装命令
5. **入口封堵** —— Redis / Docker API / MongoDB / ES / Memcached 是否监听公网（**国内挖矿木马主要入口**）
6. **防复发** —— fail2ban、禁 root 直登、禁密码登录
7. **横向排查** —— 同网段机器、`known_hosts` 里的机器（木马常沿这个列表横向移动）

### SSH 加固的正确顺序（改错会锁死自己）

```
1) 本地生成密钥          ssh-keygen -t ed25519
2) 传到服务器            ssh-copy-id -i ~/.ssh/id_ed25519.pub user@目标
3) 另开窗口测试密钥登录   ← 这步不能跳
4) 确认成功后才禁用密码登录
5) systemctl reload sshd  ← 用 reload 不用 restart，现有会话不断
```

**全程保留当前会话不要退出**，直到新会话验证成功。

## 阶段三：验证

**清完不代表干净。** 四步都过了才算：

1. **立刻重跑** `killswitch.sh --dry-run` → 应无命中
2. **重启机器后再跑一次** → 持久化没清干净的会在这步现形
3. **观察 24 小时** CPU 与出向流量 → 恢复正常才算数
4. 三步都过了，再恢复对外服务

## 找入口（不做等于白干）

按国内实际概率排序：

1. **数据库/中间件开公网无密码** —— Redis 未授权可直接写 SSH 公钥拿 root，第一大入口
2. **SSH 弱密码爆破** —— `grep "Failed password" /var/log/secure /var/log/auth.log | wc -l`，再看 `Accepted` 的陌生来源 IP
3. **应用漏洞** —— Web 目录近期修改的文件、访问日志异常请求
4. **供应链** —— 最近装过的第三方包

**没找到入口 = 会复发。** 必须明确告诉用户，不能因为"进程杀干净了"就收工。

## 业务不能断时：限速而非断网

```bash
tc qdisc add dev eth0 root tbf rate 1mbit burst 32kbit latency 400ms   # 整机限速
tc qdisc del dev eth0 root                                              # 恢复
iptables -t mangle -A OUTPUT -m owner --pid-owner <PID> -j MARK --set-mark 10   # 只限特定进程
```

---

# 模式 B：日常体检

## 核心认知：修补丁不是重点

国内 Linux 服务器沦陷的实际原因排序：

1. **数据库/中间件开在公网且无密码**（Redis、Docker API、MongoDB、ES）—— 占比最高
2. **SSH 弱密码被爆破**
3. **应用层漏洞**（Web 框架、上传点）
4. **系统包没打补丁** ← 排最后

所以体检报告里，**暴露面和 SSH 配置必须排在所有 CVE 前面**。给用户一份两百条 CVE 清单而不提"你的 Redis 开在公网上"，是本末倒置。

## 第 1 步：跑体检脚本

```bash
bash checkup.sh
```

纯只读，不改任何配置，可以在生产机随时跑。检查七类：

| 类别 | 查什么 |
|---|---|
| **暴露面** | 15 种高危服务是否监听公网；Redis/Docker 未授权访问实测 |
| **SSH** | root 直登、密码登录、空密码、默认端口、登录命令钩子、爆破迹象、fail2ban |
| **账号** | UID 0 后门账号、空密码、sudo 权限、**已授权的 SSH 公钥** |
| **木马残留** | 用特征库扫标志物；ld.so.preload、dpkgd 目录 |
| **持久化** | 可疑定时任务、近 30 天新增的 systemd 服务 |
| **文件权限** | 非标准目录的 SUID 文件、系统目录下任何人可写的文件 |
| **补丁** | 待安装的安全更新数量 |

输出按高危/中危分级，末尾给汇总。**体检发现活体木马迹象（可疑进程在跑）→ 切模式 A 处置。**

## 第 2 步：补丁深度扫描（可选）

体检脚本只给出"有多少个安全更新"。要逐个软件包的 CVE 清单，用 Trivy：

```bash
# Debian/Ubuntu
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor > /usr/share/keyrings/trivy.gpg
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" > /etc/apt/sources.list.d/trivy.list
apt-get update && apt-get install -y trivy

trivy rootfs --severity HIGH,CRITICAL --scanners vuln /
```

**Trivy 只能在目标机器上跑，没有 SSH 远程扫描功能。**

十几台以上别每台各下一份漏洞库（几百 MB），中心机跑库服务：

```bash
trivy server --listen 0.0.0.0:8080                                    # 中心机
trivy rootfs --server http://中心机IP:8080 --severity HIGH,CRITICAL /  # 业务机
```

## 第 3 步：CVE 排优先级（关键）

一台机器扫出两三百条是常态，**按 CVSS 分数排序是无用功**。把清单交给 `cve-intel` MCP 按两个维度筛：

- **CISA KEV**（已被真实攻击使用过）→ 今晚就修
- **EPSS**（未来 30 天被利用概率）→ 0.5 以上优先，0.01 以下排到下季度

CVSS 9.8 但 EPSS 0.02 的洞，紧急程度远低于 CVSS 7.5 但已进 KEV 的。

**交给用户的是 5-10 条短名单，不是原始报告。**

## 第 4 步：出整改清单

按这个顺序写，不要按脚本输出顺序：

1. **今天必须改的**——公网暴露的无密码服务、root 直登 + 密码登录、UID 0 后门账号、陌生 SSH 公钥
2. **本周改的**——装 fail2ban、SSH 换非标端口、KEV 命中的 CVE
3. **排期改的**——其余补丁、SUID 清理、权限收敛

每条写清楚**改了会影响什么**。特别是这两条容易把人锁在门外：

- 禁用密码登录前，必须先确认密钥登录已经能用，否则重连不上
- SSH 换端口前，先在云安全组放行新端口

## 加固动作的铁律

**体检只读，加固要人确认。** 生成命令 + 说明影响，由用户执行。

原因：改 SSH 配置、关服务、改防火墙都可能中断业务或把自己锁在门外，而这些机器往往没有带外管理通道。误伤代价远高于晚改几小时。

## 建议节奏

- **每周**：跑一次体检脚本，看高危项有没有新增
- **每月**：Trivy 全量扫 + KEV/EPSS 排序
- **每次上新机器**：先体检再上线业务

---

# 批量（多台机器，两个模式通用）

一台台手动跑太慢时，用 `batch.sh` 并发推到一批机器，结果收回本地汇总：

```bash
# 准备一个机器列表，每行 root@ip
cat > hosts.txt <<EOF
root@10.0.0.1
root@10.0.0.2
EOF

bash batch.sh hosts.txt                              # 批量体检（默认 checkup.sh）
bash batch.sh hosts.txt killswitch.sh --dry-run      # 批量只读排查
bash batch.sh hosts.txt triage.sh                    # 批量现场采集
```

跑完按"高危数"排序列出所有机器，哪台需要关注一目了然。

**安全闸（写死在脚本里，故意的）**：批量只准跑只读的活。批量分发 killswitch 强制要求 `--dry-run`，`--apply` 直接拒绝。**发现疑似入侵的机器，单独登录跑真杀，绝不批量处置**——一次误判会同时打到一批生产机。

前提：SSH 免密登录（密钥）已配好，且登录账号是 root 或配了免密 sudo。

# 定性（用 cve-intel MCP，别凭记忆猜）

- 可疑外连 IP → 查 IP 信誉，确认是不是已知矿池 / C2
- 样本哈希 → 查杀毒引擎，确认家族
- 定性家族后 → 查该家族已知持久化手法，照着补清
- 体检扫出的 CVE → 查 KEV / EPSS 排优先级

---

## 文件

- `scripts/killswitch.sh` —— 模式 A 止血：识别 + 杀 + 清文件（**默认动手**）
- `scripts/harden.sh` —— 模式 A 堵口：后门清除 + 入口封堵（默认只出建议）
- `scripts/triage.sh` —— 纯只读现场采集
- `scripts/checkup.sh` —— 模式 B 体检主脚本，纯只读
- `scripts/batch.sh` —— 批量分发只读检查，结果汇总（拦截一切真杀/真改）
- `feeds/malware.txt` —— 恶意特征库（两个模式共用）
