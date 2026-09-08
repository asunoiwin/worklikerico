# Relay Node Ops Skill

这是一个面向 Linux 中转机与代理节点的 Codex Skill。它优先复用用户已经选定的安装脚本，同时保护既有服务、端口和防火墙意图；也提供独立的 Shadowsocks-libev 服务端部署指引和有界监听就绪检查。

## 支持范围

- BBR 加速准备
- GOST、Brook、iptables 三类中转方式
- 独立 V2Ray 节点
- 独立 Shadowsocks-libev 服务端
- GitHub 访问受限机器的已审查下载回退
- 服务、监听、逐跳连通和重启持久性核验

目标系统包括 Ubuntu、Debian、CentOS、Rocky Linux、AlmaLinux 及其他兼容 RHEL 的发行版。

## 安全边界

- 不覆盖已有 GOST、转发或代理服务；新增链路使用独立配置与 systemd 单元。
- 不把密码、密钥和客户端配置写入命令参数、日志或公开仓库。
- 用户明确要求保留端口全开或既有防火墙策略时，只报告风险，不擅自改成严格白名单。
- 用户声明自行做客户端测试时，只验证服务端、监听、持久性和获授权的逐跳链路，不在中转机安装临时客户端。
- 交互式第三方安装脚本先下载、校验语法并记录哈希，再由用户授权执行。

## 关键修复

2026-08-24 的实机任务暴露并修复了四类可复用问题：

1. systemd 模板实例名中的连字符可能被 `%I` 按路径转义，导致 Shadowsocks 读取错误配置路径。
2. `DynamicUser=` 与 root-only 配置权限不匹配会导致服务无法读取密码配置。
3. `systemctl start` 成功不等于监听立即出现，需要有界等待。
4. 客户端验收权属于用户时，不应为了“完整测试”在中转机安装临时客户端。

根因与修复方式见 `references/troubleshooting.md`，Shadowsocks 服务端约束见 `references/shadowsocks-libev.md`。

## 验证

```bash
bash -n scripts/*.sh scripts/tests/*.sh
scripts/tests/test_wait_for_listener.sh
python /path/to/quick_validate.py .
```

`wait_for_listener.sh` 的用法：

```bash
scripts/wait_for_listener.sh SERVICE PORT 30 tcp
scripts/wait_for_listener.sh SERVICE PORT 30 udp
```

它同时检查 systemd 服务处于 active 状态和目标协议监听已出现，超时会明确失败，避免把启动竞态误判为部署失败。
