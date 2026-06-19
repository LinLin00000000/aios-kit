# Agent 辅助安装 / Agent-assisted Installation

当用户已经有 Codex、Claude Code、OpenClaw、Hermes 或其他 agent 时，推荐让 agent 先读项目，再根据真实环境动态安装。这样可以覆盖 install.sh 还没有完整测试的系统、网络和权限场景。

## 用户故事 / User story

```text
用户：https://github.com/LinLin00000000/aios-kit 帮我安装这个

Agent：
1. 浏览仓库 README 和 docs。
2. 检测系统、网络、权限、已安装组件。
3. 把每个组件作为一个问题列出来，并给默认值。
4. 让用户确认或修改每个配置项，也允许只安装某个部件。
5. 将确认结果转成 install.sh 的非交互参数。
6. 执行安装并做安装后检查。
7. 遇到问题时继续读源码/docs，修正命令或给出明确 blocker。
```

## 可直接复制给 agent 的 prompt / Copyable prompt

```text
请帮我安装这个项目：https://github.com/LinLin00000000/aios-kit

不要直接盲跑安装脚本。请按以下流程执行：

1. 先浏览 README.md 和 docs/ 下的安装文档，尤其是：
   - docs/installation.md
   - docs/installer-options.md
   - docs/mihomo-network.md
   - docs/security-and-privacy.md

2. 检测当前机器环境：
   - OS / 发行版 / 架构
   - 是否是 Ubuntu/Debian
   - 是否有 systemd
   - 是否有 sudo/root 权限
   - 是否能在不设置代理环境变量的情况下访问 GitHub/外网
   - 是否已有 Python、git、curl、node/npx、Docker、Caddy、Hermes
   - 当前 shell、HOME、PATH

3. 把安装选项整理成一个确认清单给我。每项都要给默认值和建议：
   - AIOS root，默认 ~/aios
   - 是否安装 Mihomo/Clash，默认根据直连检测决定；直连失败时默认安装
   - 是否开启 TUN，默认 yes
   - 是否恢复 apt/npm/pip/Docker 官方源，默认 yes
   - 代理配置方式：供应商订阅 URL / 本地 proxies YAML / 暂不配置
   - GitHub 镜像前缀，例如 https://gh-proxy.com/，仅在无法直连 GitHub 时使用
   - 是否安装 dev env：Python/UV、NVM+Node 24、Docker、Caddy，默认 yes
   - 是否安装 Hermes Agent，默认 yes；如果我使用 Codex/Claude/OpenClaw 且不需要 Hermes，可设 no
   - 是否安装 OPS vault，默认 yes
   - 是否添加 ~/aios/bin 到 PATH，默认 yes
   - skillpack target：默认 universal
   - skillpack mode：默认 copy

4. 等我确认后，把确认结果转换成一条非交互命令，例如：

   bash install.sh --non-interactive -y \
     --root ~/aios \
     --proxy auto \
     --reset-sources \
     --proxy-tun \
     --proxy-subscription-url '...' \
     --github-mirror https://gh-proxy.com/ \
     --with-dev-env \
     --with-hermes \
     --with-aiops \
     --add-to-path yes \
     --target universal \
     --mode copy

5. 如果系统不是 Ubuntu/Debian，或没有 systemd，请不要强行照搬 systemd/TUN 步骤。根据 docs/mihomo-network.md 调整，必要时只安装 AIOS layout、skills、OPS vault，跳过 Mihomo 或改用平台原生客户端。

6. 安装完成后运行检查：
   - ~/aios/bin/aios status
   - ~/aios/bin/aios doctor
   - 如果安装了 Mihomo：systemctl status aios-mihomo.service 或平台等价检查
   - 如果设置了 proxy helpers：proxy_test

7. 全程不要泄露或提交我的订阅 URL、UUID、token、密钥。不要把私人配置写入公开仓库。
```

## 为什么推荐 agent-assisted / Why this matters

安装脚本负责覆盖主路径；agent-assisted 安装负责处理真实世界里的长尾：

- 云厂商镜像源差异；
- 非 Ubuntu 发行版；
- 无 systemd 环境；
- 已有 agent，不需要 Hermes；
- 私有订阅/节点格式差异；
- 权限、网络、企业代理等复杂情况。

AIOS 的目标不是让 shell 脚本假装知道所有环境，而是让 docs、installer 和 agent 协同完成安装。
