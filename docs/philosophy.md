# AIOS 理念 / Philosophy

`aios-kit` 不是一个“大而全平台”，而是一个面向个人 AI 操作系统的轻量分发骨架。

它追求的是：

- **可迁移**：新机器可以从公开仓库和模板重新生成，不依赖维护者私人路径。
- **可审计**：重要状态写在文件系统、manifest、vault 和日志里，避免隐藏魔法。
- **可组合**：Hermes Agent 是默认中心，但 Codex、Claude Code、OpenClaw 等 agent 也可以使用其中的 skills、OPS vault、LLL 工作流和项目注册结构。
- **保守幂等**：先检测，再执行；已经存在的组件不重复安装；本地改动不默认覆盖。
- **Agent-friendly**：README 和 docs 同时给人和 agent 读。已有 agent 可以先浏览项目，再按用户环境动态选择组件，而不是盲跑 shell。

## 为什么以 Hermes Agent 为基础 / Why Hermes first

Hermes 适合作为长期上下文、工具调用、调度和多 worker 编排入口，因此 `aios-kit` 默认以 Hermes 为中心组织 skills 和运维资料。但 AIOS 的边界不应该锁死在单一 agent 上：

- runtime skills 默认安装到通用 `~/.agents/skills`；
- Hermes 安装是可选项，可用 `--no-hermes` 跳过；
- OPS vault、LLL、项目 registry 都是普通文件系统结构；
- agent-assisted installation 允许其他 agent 读取本文档后按环境执行。

## 产品边界 / Product boundary

公开 installer 只做干净默认值，不导出作者机器上的历史路径、私人订阅、密钥、live vault 或本地 overlay。

本地迁移可以自己做 symlink 和兼容路径，但那不应该成为 public default。
