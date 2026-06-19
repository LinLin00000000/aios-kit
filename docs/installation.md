# 安装流程 / Installation Flow

当前安装器主要在 Ubuntu/Debian 系云服务器上验证。其他发行版建议先使用 `--dry-run` 或让已有 agent 读源码后辅助安装。

## 快速安装 / Quick install

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)"
```

如果还不能直连 GitHub，可以用你信任的 raw/release 镜像：

```bash
bash -c "$(curl -fsSL https://gh-proxy.com/https://raw.githubusercontent.com/LinLin00000000/aios-kit/main/install.sh)" -- --github-mirror https://gh-proxy.com/
```

## 安装步骤 / Steps

安装器按以下顺序执行。每一步都尽量幂等：先检测，再执行。

1. **最小依赖检查**
   - 需要 `git`、`python3`。
   - 如果 `node/npx` 不存在，会提示 dev-env 阶段安装 NVM + Node 24。

2. **直连网络测试**
   - 在不使用代理环境变量的情况下请求 GitHub。
   - 如果直连可用，默认跳过 Mihomo。
   - 如果直连失败：交互式询问是否安装 Mihomo，默认 yes；非交互 `--proxy auto` 默认安装。

3. **准备 AIOS root**
   - 默认 `~/aios`。
   - 创建 `modules/`、`bin/` 等结构。

4. **准备 aios-kit checkout**
   - 默认位置 `~/aios/modules/aios-kit`。
   - 如果当前脚本就在 repo 内运行，则使用当前 repo。

5. **安装 `aios` command shim**
   - 写入 `~/aios/bin/aios`。
   - 可选择是否添加到 PATH。

6. **Mihomo/Clash 网络组件**
   - 仅当 `--proxy yes`，或 `--proxy auto` 检测直连失败并确认安装时执行。
   - 生成 `~/aios/network/mihomo/config.yaml`。
   - 下载 Mihomo 内核到 `~/aios/network/mihomo/mihomo`。
   - 在 Linux/systemd 上写入 `/etc/systemd/system/aios-mihomo.service` 并 enable/start。
   - 写入 `proxy_on` / `proxy_off` / `proxy_test` / `proxy_restart` shell helpers。

7. **恢复官方源**
   - 作为独立步骤执行，交互式会询问，默认 yes。
   - npm：删除自定义 registry。
   - pip：删除 `global.index-url`。
   - Docker：由 Docker 官方安装步骤配置。
   - apt：Ubuntu 上备份旧 source，并写入官方 Ubuntu deb822 source；其他发行版暂时只提示。

8. **开发环境**
   - Python / `python3-venv`
   - UV
   - NVM + Node 24
   - Docker
   - Caddy

9. **AIOS instance 初始化**
   - 记录 root、OPS vault、skills dir 等路径。

10. **LLL 模块**
   - 默认 clone/update `lins-living-loop` 到 `~/aios/modules/lins-living-loop`。

11. **Hermes Agent（可选）**
   - 默认安装/检测 Hermes。
   - 可用 `--no-hermes` 跳过，适合 Codex、Claude Code、OpenClaw 等用户只使用 AIOS 的通用部分。

12. **Skillpack**
   - 默认安装到通用 runtime skills dir：`~/.agents/skills`。
   - 默认 copy mode。
   - 更新时保护本地修改，除非显式 `--force`。

13. **OPS vault 模板**
   - 默认从公开模板初始化 `~/aios/vault/ops`。
   - 不复制维护者私人 live vault。

## 安装后检查 / Post-install checks

```bash
aios status
aios doctor
aios update --dry-run
systemctl status aios-mihomo.service
proxy_test
```

如果没有把 `aios` 加入 PATH：

```bash
~/aios/bin/aios status
```
