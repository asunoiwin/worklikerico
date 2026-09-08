# Oracle Cloud Ops Skill

面向 Codex 的 Oracle Cloud Infrastructure（OCI）安全运维 Skill。它覆盖账户盘点、可用区与配额查询、计算实例生命周期、重装与网络配置、SSH/root 登录，以及免费机器池容量不足时的有界定时抢机。

这个项目的重点不是把 OCI 命令简单包一层，而是为高风险云操作提供明确的目标确认、费用边界、幂等控制、验证和回滚要求。

## 功能

| 能力 | 实现方式 | 默认安全边界 |
| --- | --- | --- |
| 账户、Home Region、订阅区域、可用区 | OCI 官方 SDK/CLI | 只读 |
| 计算配额、使用量、剩余额度 | Limits API | 区分配额与物理容量 |
| 实例、启动盘、VNIC、公网 IP 盘点 | `oci_inventory.py` | OCID 默认只显示后缀 |
| 开机、关机、重启 | OCI Compute API/CLI | 写操作前解析唯一实例 |
| 重装或重建 | 启动盘替换或并行重建方案 | 不自动删除旧实例或旧盘 |
| 子网、路由、安全列表、NSG、公网 IP | OCI Networking API/CLI | 禁止静默扩大公网暴露 |
| SSH 密钥、普通用户密码、root 密码登录 | SSH、cloud-init、控制台恢复 | 密码不进入命令行和日志 |
| 创建实例并配置 root 密码 | 哈希后的 cloud-init + SSH 密钥回退 | 保留密钥登录通道 |
| 容量不足时定时抢机 | 有界重试状态机 | 区分 START 与 LAUNCH，成功后自动停止 |
| macOS 每分钟调度 | LaunchAgent `StartInterval=60` | 使用系统级调度，不依赖 Codex 会话常驻 |
| Always Free 低活跃防回收 | 受控 CPU/内存守护进程 | 明确选择后安装；不刷流量、不保证保留 |

## 安全原则

- Skill 和仓库中不得保存 OCI 私钥、密码、完整 User Data 或真实账户配置。
- 只读查询可以直接执行；云端写操作必须先确认 profile、区域、资源 OCID、当前状态、费用影响和回滚方式。
- 不自动删除实例、启动盘、保留公网 IP、VNIC 或 SSH 密钥。
- `START` 是启动现有实例，`LAUNCH` 是创建新实例，两者不会混用。
- 配额剩余不代表物理机器池有货，也不等于当前操作一定属于免费额度。
- 重试任务必须有最大次数、持久状态、文件锁和终止条件；禁止无界循环或并发轰炸 API。
- 开启密码登录前应先限制 TCP/22 的来源，并保留已验证的 SSH 密钥会话。
- 防回收守护程序会有意消耗空闲 CPU/内存，必须明确选择后才能安装；禁止刷带宽、挖矿或运行未经审计的第三方一键脚本。

完整边界见 [`SKILL.md`](SKILL.md)。

## 安装

### 作为 Codex Skill 安装

```bash
git clone https://github.com/asunoiwin/oracle-cloud-ops-skill.git \
  ~/.codex/skills/oci-cloud-ops
```

重新启动 Codex，或让 Codex 重新发现本地 Skills。

### 依赖

- Python 3.10+
- [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm)：实例操作和抢机脚本需要
- OCI Python SDK：账户盘点脚本需要
- OpenSSL：生成 root 密码 cloud-init 时需要
- macOS `launchd`：仅 macOS 每分钟调度需要

建议在隔离环境安装 SDK：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install oci
```

## OCI 认证

使用 `~/.oci/config` 中的命名 profile，不要把私钥内容粘贴到命令、README 或 Skill：

```ini
[MY_ACCOUNT]
user=ocid1.user...
fingerprint=xx:xx:xx:xx
tenancy=ocid1.tenancy...
region=ap-tokyo-1
key_file=/absolute/path/to/oci_api_key.pem
```

配置文件和私钥都应设置为仅当前用户可读：

```bash
chmod 600 ~/.oci/config /absolute/path/to/oci_api_key.pem
```

## 使用示例

### 1. 查询账户、可用区、配额和机器

```bash
python scripts/oci_inventory.py \
  --profile MY_ACCOUNT \
  --output /secure/path/oci-inventory.json
```

可以重复提供 `--profile`，一次盘点多个账户。输出文件权限为 `0600`，默认忽略已经终止的实例并对 OCID 脱敏。

### 2. 生成 root 密码登录 cloud-init

```bash
python scripts/render_root_cloud_init.py \
  --output /secure/path/root-login.yaml
```

脚本交互式读取两次密码，只把 SHA-512 哈希写入权限为 `0600` 的文件。创建实例时仍应同时配置 SSH 公钥作为恢复通道。

### 3. 对创建请求执行一次抢机尝试

先用 OCI CLI 生成完整请求模板，逐项确认镜像、shape、OCPU、内存、启动盘、子网、可用区和 SSH 公钥：

```bash
oci compute instance launch --generate-full-command-json-input > /secure/path/launch.json
```

先做本地 dry-run：

```bash
python scripts/oci_capacity_retry.py launch \
  --profile MY_ACCOUNT \
  --region ap-tokyo-1 \
  --request-file /secure/path/launch.json \
  --state-file /secure/path/launch-state.json \
  --max-attempts 120 \
  --once \
  --dry-run
```

确认无误后去掉 `--dry-run`。脚本会区分容量不足、限额、权限、参数错误、限流和不确定网络失败，并使用持久化状态避免重复创建。

### 4. 每分钟启动现有的 STOPPED 实例

先生成 macOS LaunchAgent：

```bash
python scripts/render_macos_launchagent.py start \
  --label com.example.oracle-capacity-retry \
  --profile MY_ACCOUNT \
  --region ap-tokyo-1 \
  --instance-id ocid1.instance... \
  --state-file /secure/path/start-state.json \
  --stdout /secure/path/start.stdout.log \
  --stderr /secure/path/start.stderr.log \
  --output "$HOME/Library/LaunchAgents/com.example.oracle-capacity-retry.plist"
```

加载任务：

```bash
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.example.oracle-capacity-retry.plist"
```

停止并卸载：

```bash
launchctl bootout "gui/$(id -u)/com.example.oracle-capacity-retry"
```

LaunchAgent 每 60 秒执行一个 `--once` tick。实例已经运行、任务成功、达到最大次数或出现限额、权限、参数等终止错误后，不会继续发起写请求。

### 5. 部署受控低活跃防回收守护程序

Oracle 当前政策允许回收连续 7 天处于低活跃状态的 Always Free 计算实例。两个机型使用独立固定配置：A1 不烧 CPU，只把整机总内存补到 25%，应用用量上升时立即释放；E2 不占内存，每 2 小时运行一次最长 15 分钟的 25% CPU 脉冲。E2 在一分钟采样下约有 12.5% 样本处于高位，P95 理论值接近 25%，时间加权平均占用约 3.1%。程序只读取本机 `/proc`，不调用 OCI API、不需要云端 Key、不产生网络流量。

网络的 20% 是 Oracle 闲置判定条件，不是每月流量额度。当前官方规格为 E2 公网最高 50 Mbps、同区域/私网最高 480 Mbps；A1 每 OCPU 最高 1 Gbps。Always Free 当前另含租户级每月 10 TB 出站数据。防回收程序不刷网络，因为只需让一个适用指标不再同时处于低活跃状态。

先查看安装计划：

```bash
sudo python3 scripts/install_linux_idle_guard.py install \
  --shape a1 \
  --dry-run
```

确认资源影响和卸载方案后，去掉 `--dry-run`。E2 Micro 使用 `--shape e2`，安装器会启用 `oracle-idle-guard.timer`，而不是把服务常驻运行。A1/E2 的目标均为固定配置，安装器会拒绝自定义目标，避免配置漂移后仍被误报为健康。

检查状态：

```bash
sudo python3 scripts/install_linux_idle_guard.py status
systemctl list-timers oracle-idle-guard.timer --no-pager
journalctl -u oracle-idle-guard.service --since '15 minutes ago' --no-pager
```

精确卸载：

```bash
sudo python3 scripts/install_linux_idle_guard.py uninstall --dry-run
sudo python3 scripts/install_linux_idle_guard.py uninstall
```

该程序不是 Oracle 官方工具，也不能保证实例一定不会被回收。部署前仍应做好数据备份和重建预案。完整说明见 [`references/idle-reclaim.md`](references/idle-reclaim.md)。

## 项目结构

```text
.
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
│   ├── inventory.md
│   ├── operations.md
│   ├── capacity-retry.md
│   └── idle-reclaim.md
└── scripts/
    ├── oci_inventory.py
    ├── oci_capacity_retry.py
    ├── oracle_idle_guard.py
    ├── install_linux_idle_guard.py
    ├── render_macos_launchagent.py
    ├── render_root_cloud_init.py
    └── tests/
        └── test_scripts.py
```

## 测试

```bash
python3 -m unittest discover -s scripts/tests -p 'test_*.py' -v
```

当前测试覆盖：

- 容量不足后重试及 retry token 轮换
- 不确定失败时复用 retry token
- 配额和权限类错误终止
- 现有实例状态检查及启动后复查
- 请求、profile、区域和最大次数变更保护
- 私钥材料拒绝
- root 密码哈希、错误路径和输出权限
- 账户报告 OCID 脱敏和配置文件权限检查
- LaunchAgent 60 秒间隔和 `--once` 调用约束
- 防回收控制器的 CPU 自动退让、E2 稀疏脉冲、A1 内存目标和 30% 硬上限
- systemd 网络隔离、资源上限、沙箱安装和精确卸载

## 已验证边界

开发时已完成本地单元测试、macOS LaunchAgent 60 秒双周期触发测试和真实 OCI 只读 API 验收。真实开关机、重装、网络修改、密码修改或创建实例具有停机、失联或费用风险，不应在通用测试中自动执行。

## 免责声明

本项目是运维辅助工具，不替代 Oracle 官方文档、费用核算或变更审批。执行任何云端写操作前，请重新核对当前 OCI 服务限制、Always Free 政策、区域支持、镜像兼容性和预计费用。
