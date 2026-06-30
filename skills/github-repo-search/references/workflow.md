# github-repo-search workflow

本 skill 的标准形态是 **scripted collection + AI judgment**：脚本承担可重复、可缓存、可验证的机械流程，AI 只读压缩证据并做语义判断、分类、推荐理由和限制说明。

## 标准执行路径

1. 把用户需求转成 3-10 条 query，写入 `search-plan.json` 或临时 `queries.json`。
2. 运行脚本：

   ```bash
   python3 <skill>/scripts/github_repo_search.py \
     --queries queries.json \
     --out /tmp/github-search-run \
     --limit-per-query 30 \
     --min-stars 100 \
     --top-k 40 \
     --readme-top-n 40 \
     --proxy http://127.0.0.1:7890 \
     --prefer-gh
   ```

3. 只把 `<out>/ai-brief.md` 或 `<out>/ai-input-top<N>.md` 读入上下文。
4. 必要时只深读 Top 3-5 的缓存 README：`<out>/repos/<owner>__<repo>/readme.md`。
5. 最终报告引用 `manifest.json` 中的检索时间、召回数量、过滤数量、rate limit 摘要和错误情况。

## 降载规则

如果 provider/model 出现 `stream_error`、`context canceled`、`Invalid API response`、长时间无响应：

- 不要启动同形大 subagent 重试；
- 先检查脚本产物是否已经生成；
- 如果已有 `ai-brief.md`，由 supervisor 内联完成判断；
- 如果没有，缩小 `--limit-per-query`、`--readme-top-n`、`--top-k` 后重跑脚本；
- 不把完整 README dump 塞进模型上下文。

## AI 负责的判断

- query plan 的语义设计和同义词扩展；
- 判断 repo 类型：应用产品层、通用框架层、MCP 服务层、目录清单层、方法论/研究层等；
- 剔除“关键词命中但场景不合适”的噪音；
- 根据用户目标重排 Top N；
- 写“是什么 + 为什么推荐 + 限制/风险”；
- 标注哪些判断有脚本证据，哪些是推测。

## 脚本负责的事实层

- `gh` / GitHub API 调用、proxy、retry、timeout；
- 搜索召回、去重、硬过滤；
- metadata/topics/README 抓取与缓存；
- README heading、first paragraphs、keyword snippets、install/docs signals 抽取；
- 机械启发式预筛；
- 产物落盘与错误记录。
