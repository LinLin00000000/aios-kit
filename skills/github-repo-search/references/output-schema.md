# github_repo_search.py output schema

脚本输出目录结构：

```text
out/
├── manifest.json
├── queries.json
├── raw/search-<query-id>.json
├── repos.json
├── repos.filtered.json
├── repos/<owner>__<repo>/
│   ├── metadata.json
│   ├── readme.md
│   ├── readme.meta.json
│   └── evidence.json
├── evidence.jsonl
├── candidates.jsonl
├── candidates.compact.json
├── candidates.md
├── ai-input-top<N>.md
├── ai-brief.md
└── errors.jsonl              # only when non-fatal failures occurred
```

## manifest.json

关键字段：

- `started_at` / `finished_at`: UTC ISO 时间。
- `topic`: 检索主题。
- `raw_count`: 各 query 原始召回合计。
- `deduped_count`: 按 `owner/repo` 去重后的数量。
- `filtered_count`: 硬过滤后的数量。
- `candidate_count`: 进入候选输出的数量。
- `rate_limit_summary`: gh rate limit 摘要。
- `proxy_used`: 实际使用的 proxy（不会包含 token）。

### 可选 `source_acquisition`

默认搜索 run 不包含完整 clone，因此旧 manifest 和 candidate schema 保持不变。只有少数选定仓库进入源码深读时，调用方可以在当前 Worksite 的 evidence/manifest 中增加可选记录；共享 cache 自身不拥有这份解释关系：

```json
{
  "source_acquisition": [
    {
      "schema": "aios.github-source-cache-receipt.v1",
      "repository": "owner/repo",
      "commit": "0123456789abcdef0123456789abcdef01234567",
      "retrieved_at": "2026-01-01T00:00:00+00:00",
      "mode": "reused_commit",
      "cache_path": "~/aios/cache/github/repos/owner/repo.git",
      "worktree_path": "internal/sources/owner__repo",
      "cited_paths": ["src/example.py"]
    }
  ]
}
```

字段要求：

- `repository` 使用 canonical `owner/repo`；`commit` 必须是 full SHA。
- `worktree_path`、`cited_paths` 只记录当前 Worksite 需要的非秘密定位信息，字段均可选。
- 不记录 credential URL、token、secret argv、README/源码全文或调研解释。
- `source_acquisition` 缺失表示本次只使用搜索/README evidence，不是错误。

## candidate item

`candidates.jsonl` 每行包含：

- `repo`: GitHub metadata。
  - `full_name`, `url`, `description`, `stars`, `forks`, `open_issues`
  - `language`, `license`, `topics`
  - `archived`, `fork`, `private`
  - `updated_at`, `pushed_at`, `default_branch`
  - `matched_queries`, `query_purposes`
- `readme`: 脚本抽取的证据。
  - `available`, `readme_chars`
  - `headings`, `first_paragraphs`
  - `keyword_hits`: keyword -> snippets
  - `install_signals`, `docs_signals`
  - `section_snippets`
- `heuristic`: 机械预筛分数。
  - `base_score`, `freshness_score`, `readme_score`, `keyword_relevance`, `topic_match`, `query_hit_score`

`heuristic.base_score` 只用于减少模型阅读负担，不是最终推荐排序。
