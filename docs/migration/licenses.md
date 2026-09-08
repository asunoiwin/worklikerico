# 许可证边界

统一仓库根许可证为 MIT。下列包带有独立 MIT 证据并在目标目录保留许可证副本：Memory Pro、Claude Autoagent、Codex Multi-Agent、Claude/Codex Design Test Loop、Linux Guard。

OCI Cloud Ops 与 Relay Node Ops 的旧独立仓库没有检测到许可证文件；它们由同一所有者维护，本次仅搬入统一仓库并受根许可证覆盖。若需要保留旧仓库作为独立分发源，应分别补许可证后再发布新版本。

其余从个人 skills 安装目录纳入的自建能力没有独立许可证文件，按统一仓库根许可证分发。第三方系统 skill、官方/策展插件及 vendor cache 没有复制，只在 `catalog/third-party.json` 记录依赖关系。
