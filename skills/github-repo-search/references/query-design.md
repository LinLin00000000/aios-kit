# Query design for GitHub repo search

AI 先设计 query，再交给脚本批量执行。query 不追求一次命中全部，而是覆盖正交召回方向。

## 推荐 query 维度

- 核心主题词：用户直接说的领域词。
- 同义词/别名：英文缩写、生态内惯用叫法、替代表达。
- 场景词：webui、local、self-hosted、agent、workflow、mcp、rag、dashboard、cli、server。
- 形态词：framework、platform、toolkit、awesome、curated、examples、template。
- 技术词：Python、TypeScript、Go、Docker、React、FastAPI 等。

## 默认策略

- 3-10 条 query；一般任务 5 条左右即可。
- **GitHub repository search 的普通空格词通常按 AND 收窄**；每条 query 默认保持 2–4 个高辨识度词。不要把完整需求句或 6–8 个维度塞进一条 query，否则可能出现“脚本成功但几乎零召回”。复杂需求应拆成更多正交短 query。
- 先用 1–2 条短 query 做 smoke，确认召回数量合理，再执行完整批次；若 `raw_count` 异常低，先用 `gh search repos '<short query>' --limit 5` 对照，修正 query 后再判断候选缺失。
- 不在 query 中塞太多负例；负例放过滤/AI 判断阶段。
- 每条 query 写 `purpose`，用于最终报告解释召回边界。
- 高成本 full LLL 调研可以提高 `--limit-per-query`，但优先扩大 query 覆盖，不优先增大单 query 深度。

## search-plan.json 示例

```json
{
  "topic": "AI 多媒体 WebUI",
  "constraints": {
    "min_stars": 100,
    "archived": false,
    "fork": false
  },
  "queries": [
    {"id": "core", "query": "AI multimedia webui", "purpose": "核心召回：多媒体 AI WebUI"},
    {"id": "video", "query": "AI video generation webui", "purpose": "视频生成 WebUI"},
    {"id": "image", "query": "AI image generation webui", "purpose": "图像生成 WebUI"},
    {"id": "local", "query": "local AI webui", "purpose": "本地运行形态"},
    {"id": "self-hosted", "query": "self-hosted webui", "purpose": "自托管形态"},
    {"id": "comfy", "query": "ComfyUI alternative", "purpose": "ComfyUI 生态与替代项目"}
  ]
}
```
