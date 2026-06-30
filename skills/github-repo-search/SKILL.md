---
name: github-repo-search
description: 帮助用户搜索、筛选和比较 GitHub 开源项目，输出结构化推荐报告。触发于“帮我找开源项目”“搜 GitHub 仓库”“找 XX 方向 repo”“开源项目推荐”“github 搜索”等；默认使用 bundled script 先做 GitHub 召回、去重、metadata/README 抓取、缓存和压缩证据，再由 AI 做语义判断、分类和推荐说明。
---

# GitHub 开源项目搜索助手

## 核心定位

从用户自然语言需求出发，经过 query 设计、脚本化 GitHub 召回、硬过滤、证据摘录、AI 语义重排，最终产出可比较、可决策、可行动的开源项目推荐报告。

核心原则：

> 广度由脚本承担，深度由模型承担；证据由脚本缓存，判断由模型完成。

## 适用范围

- 数据源：GitHub 公开仓库。
- 默认优先使用已认证 `gh` CLI；失败时可 HTTP fallback。
- 默认网络参数：`HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7890`，可用参数覆盖或 `--no-proxy` 禁用。
- 默认硬过滤：`stars >= 100`、`archived=false`、`is:public`、默认排除 fork。
- 默认输出：单榜 Top N，榜单内标注仓库归属类型。
- 本流程默认不包含安装与落地实施，除非用户另行要求。

## 重要：脚本优先

GitHub 搜索、metadata 抓取、README 拉取、缓存、去重、初筛必须优先使用：

```bash
python3 <skill>/scripts/github_repo_search.py --help
```

不要让多个 subagent 各自重复执行完整 GitHub 搜索和 README 深读。模型只应读取脚本生成的 `ai-brief.md`，必要时再深读少数缓存 README。

更多细节见：

- `references/workflow.md`
- `references/output-schema.md`
- `references/query-design.md`
- `templates/search-plan.json`

## 标准工作流程

### 1. 需求收敛，但不要过度阻塞

先把用户需求整理成可执行假设：

```text
核心诉求：
- 主题：xxx
- 数量：Top N（默认 Top 10）
- 最低 stars：>= 100
- 排序模式：相关性优先（默认）/ 星标优先
- 目标形态：可直接使用的产品 / 可二次开发的框架 / 资料清单 / 方法论
- 偏好：xxx（可空）
- 排除：xxx（可空）
```

当用户已经明确主题、数量、用途，或明确说“直接开始/不用确认”时，不要停下来等待确认；把缺省值写成假设后直接执行脚本。只有当目标会显著改变 query 设计或成本很高时才追问。

### 2. 设计 query plan

生成 3-10 条 query，每条包含 `id`、`query`、`purpose`。优先覆盖正交方向：核心词、同义词、场景词、技术词、形态词。

保存到临时文件，例如：

```bash
/tmp/github-search-run/queries.json
```

### 3. 运行脚本建立候选池

推荐命令：

```bash
python3 <skill>/scripts/github_repo_search.py \
  --queries /tmp/github-search-run/queries.json \
  --out /tmp/github-search-run \
  --limit-per-query 30 \
  --min-stars 100 \
  --top-k 40 \
  --readme-top-n 40 \
  --proxy http://127.0.0.1:7890 \
  --prefer-gh
```

小规模 smoke 或快速任务可降低参数：

```bash
python3 <skill>/scripts/github_repo_search.py \
  --query "agent memory framework" \
  --out /tmp/github-search-smoke \
  --limit-per-query 5 \
  --min-stars 100 \
  --top-k 5 \
  --readme-top-n 3
```

### 4. 只读压缩 AI 输入

优先读取：

```text
<out>/ai-brief.md
```

或：

```text
<out>/ai-input-top<N>.md
```

不要把完整 README dump 批量塞进模型上下文。若需要深读，只打开 Top 3-5 的：

```text
<out>/repos/<owner>__<repo>/readme.md
```

### 5. AI 判断与推荐报告

AI 负责：

- 判断每个 repo 的真实角色与边界；
- 剔除关键词命中但不适合的噪音；
- 按用户场景重排 Top N；
- 写“是什么 + 为什么推荐 + 限制/风险”；
- 区分脚本证据、README 证据和模型推测。

## 交付格式

最终报告包含：

1. 需求摘要
2. 检索词清单（query + purpose）
3. 筛选与重排规则
4. 结果总览（原始召回/去重后/过滤后/进入 AI 评审）
5. Top N 单榜表格
6. 结论与下一步建议

Top N 表格字段：

| 仓库 | 星标 | 仓库归属类型 | 项目介绍（是什么 + 推荐理由） | 其它信息补充 | 链接 |
|---|---:|---|---|---|---|

其它信息补充建议含：语言 / License / 最近更新时间 / 上手复杂度 / 风险提示。

## 仓库归属类型字典

- 通用框架层
- 应用产品层（可直接使用）
- 记忆层/上下文基础设施
- MCP 服务层
- 目录清单层（awesome/curated）
- 垂直场景方案层
- 方法论/研究层

## 降载与故障处理

如果模型/provider 出现 `stream_error`、`context canceled`、`Invalid API response`、长时间无响应：

1. 不要启动同形大 subagent 重试。
2. 检查脚本产物是否已生成。
3. 若已有 `ai-brief.md`，由 supervisor 内联完成判断。
4. 若没有产物，缩小 `--limit-per-query`、`--readme-top-n`、`--top-k` 后重跑脚本。
5. 报告中区分“工具/网络失败”和“没有找到项目”，不要把 worker 失败当作证据缺失。

## 质量检查清单

- 是否明确用户目标、Top N、默认 stars 和目标形态？
- 是否运行了脚本，而不是手工重复搜索？
- 是否记录检索时间、召回/去重/过滤数量和 rate limit 摘要？
- 是否只把 `ai-brief.md`/Top 候选摘要输入模型？
- 是否完成仓库归属类型分类？
- 是否每个推荐都包含“是什么 + 为什么推荐 + 限制/风险”？
- 是否将脚本分数仅作为预筛，不冒充最终判断？
