#!/usr/bin/env python3
"""GitHub repository search pipeline for the github-repo-search skill.

The script handles mechanical collection so the model can focus on judgment:
- gh CLI first, HTTP fallback where practical
- proxy + retry + timeout
- search, dedupe, hard filtering
- metadata/topics enrichment
- README fetch/cache
- evidence/snippet extraction
- compact AI input rendering

It intentionally uses only the Python standard library so it can run in a fresh
AIOS/Hermes environment without package installation.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import math
import os
import random
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

DEFAULT_PROXY = "http://127.0.0.1:7890"
SEARCH_FIELDS = [
    "fullName",
    "description",
    "stargazersCount",
    "url",
    "isArchived",
    "isDisabled",
    "isFork",
    "isPrivate",
    "language",
    "license",
    "updatedAt",
    "pushedAt",
    "createdAt",
    "visibility",
    "forksCount",
    "watchersCount",
    "openIssuesCount",
    "homepage",
    "defaultBranch",
]
REPO_VIEW_FIELDS = [
    "nameWithOwner",
    "description",
    "url",
    "stargazerCount",
    "forkCount",
    "watchers",
    "issues",
    "isArchived",
    "isFork",
    "isPrivate",
    "primaryLanguage",
    "licenseInfo",
    "repositoryTopics",
    "updatedAt",
    "pushedAt",
    "createdAt",
    "defaultBranchRef",
    "homepageUrl",
]
DEFAULT_KEYWORDS = [
    "webui", "web ui", "ui", "dashboard", "gui",
    "agent", "agents", "mcp", "rag", "memory", "workflow",
    "image", "video", "audio", "multimodal", "multi-modal",
    "local", "self-host", "selfhost", "docker", "compose", "quickstart", "install",
    "api", "sdk", "plugin", "extension", "examples", "demo",
]
INSTALL_KEYWORDS = ["docker", "docker compose", "pip install", "npm install", "pnpm", "uv", "conda", "one-click", "quick start", "quickstart"]
DOC_KEYWORDS = ["docs", "documentation", "examples", "demo", "tutorial", "guide", "quickstart", "quick start"]
TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class PipelineError(Exception):
    pass


class RateLimitError(PipelineError):
    pass


class NotFoundError(PipelineError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_repo_dir(full_name: str) -> str:
    return full_name.replace("/", "__")


def read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    mkdir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def append_jsonl(path: Path, data: dict[str, Any]) -> None:
    mkdir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    mkdir(path.parent)
    path.write_text(text, encoding="utf-8")


def setup_env(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    if not args.no_proxy:
        proxy = args.proxy or env.get("HTTPS_PROXY") or env.get("HTTP_PROXY") or DEFAULT_PROXY
        env.setdefault("HTTP_PROXY", proxy)
        env.setdefault("HTTPS_PROXY", proxy)
        env.setdefault("NO_PROXY", "localhost,127.0.0.1,::1")
        if args.set_all_proxy:
            env.setdefault("ALL_PROXY", proxy)
    return env


def retry_call(
    fn: Callable[[], Any],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
    label: str = "operation",
) -> Any:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except NotFoundError:
            return None
        except RateLimitError:
            raise
        except Exception as exc:  # noqa: BLE001 - CLI/network wrappers normalize below
            last = exc
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2 ** i)) + random.random() * 0.25
            time.sleep(delay)
    raise PipelineError(f"{label} failed after {attempts} attempts: {last}") from last


def run_gh_json(args: list[str], *, env: dict[str, str], timeout: int, label: str, retries: int) -> Any:
    cmd = ["gh", *args]

    def once() -> Any:
        proc = subprocess.run(
            cmd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            low = stderr.lower()
            if "not found" in low or "http 404" in low:
                raise NotFoundError(stderr)
            if "rate limit" in low or "http 403" in low or "http 429" in low:
                raise RateLimitError(stderr)
            raise PipelineError(f"gh {' '.join(args[:4])} exited {proc.returncode}: {stderr[:500]}")
        out = proc.stdout.strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise PipelineError(f"{label} returned non-JSON: {out[:500]}") from exc

    return retry_call(once, attempts=retries, label=label)


def http_json(url: str, *, env: dict[str, str], timeout: int, token: str | None = None, retries: int = 3) -> Any:
    # urllib honors *_proxy environment variables via getproxies(); install an opener
    # after temporarily setting os.environ would be global, so pass ProxyHandler explicitly.
    proxies: dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        if env.get(key):
            proxies[key.split("_")[0].lower()] = env[key]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))

    def once() -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "aios-github-repo-search-skill",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(url)
            if exc.code in (403, 429):
                raise RateLimitError(f"HTTP {exc.code}: {url}")
            if exc.code in TRANSIENT_STATUS:
                raise PipelineError(f"HTTP {exc.code}: {url}")
            raise

    return retry_call(once, attempts=retries, label=f"GET {url}")


def http_text(url: str, *, env: dict[str, str], timeout: int, retries: int = 3) -> str | None:
    proxies: dict[str, str] = {}
    for key in ("HTTP_PROXY", "HTTPS_PROXY"):
        if env.get(key):
            proxies[key.split("_")[0].lower()] = env[key]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies))

    def once() -> str | None:
        req = urllib.request.Request(url, headers={"User-Agent": "aios-github-repo-search-skill"})
        try:
            with opener.open(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise NotFoundError(url)
            if exc.code in TRANSIENT_STATUS:
                raise PipelineError(f"HTTP {exc.code}: {url}")
            raise

    return retry_call(once, attempts=retries, label=f"GET {url}")


def load_queries(args: argparse.Namespace) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    topic = args.topic or "GitHub repository search"
    constraints: dict[str, Any] = {}
    queries: list[dict[str, str]] = []
    if args.queries:
        data = read_json_file(Path(args.queries))
        if isinstance(data, list):
            for i, item in enumerate(data, 1):
                if isinstance(item, str):
                    queries.append({"id": f"q{i:02d}", "query": item, "purpose": "user supplied"})
                else:
                    queries.append({
                        "id": str(item.get("id") or f"q{i:02d}"),
                        "query": str(item["query"]),
                        "purpose": str(item.get("purpose") or "user supplied"),
                    })
        elif isinstance(data, dict):
            topic = str(data.get("topic") or topic)
            constraints = dict(data.get("constraints") or {})
            raw_queries = data.get("queries") or []
            for i, item in enumerate(raw_queries, 1):
                if isinstance(item, str):
                    queries.append({"id": f"q{i:02d}", "query": item, "purpose": "user supplied"})
                else:
                    queries.append({
                        "id": str(item.get("id") or f"q{i:02d}"),
                        "query": str(item["query"]),
                        "purpose": str(item.get("purpose") or "user supplied"),
                    })
        else:
            raise SystemExit("--queries must be a JSON object or list")
    for q in args.query or []:
        queries.append({"id": f"q{len(queries)+1:02d}", "query": q, "purpose": "CLI supplied"})
    if not queries:
        raise SystemExit("Provide --queries <json> or at least one --query")
    return topic, constraints, queries


def normalize_repo_from_search(item: dict[str, Any]) -> dict[str, Any]:
    license_obj = item.get("license") or {}
    if isinstance(license_obj, dict):
        license_name = license_obj.get("spdxId") or license_obj.get("name")
    else:
        license_name = license_obj
    return {
        "full_name": item.get("fullName") or item.get("full_name") or item.get("nameWithOwner"),
        "description": item.get("description") or "",
        # gh search returns a browser URL in `url`; REST search returns an API
        # URL in `url` and the browser URL in `html_url`, so prefer html_url.
        "url": item.get("html_url") or item.get("url"),
        "stars": int(item.get("stargazersCount") or item.get("stargazerCount") or item.get("stargazers_count") or 0),
        "forks": int(item.get("forksCount") or item.get("fork_count") or item.get("forks_count") or 0),
        "watchers": int(item.get("watchersCount") or item.get("watchers") or item.get("watchers_count") or 0),
        "open_issues": int(item.get("openIssuesCount") or item.get("open_issues_count") or 0),
        "language": item.get("language") or item.get("primaryLanguage") or "",
        "license": license_name or "",
        "archived": bool(item.get("isArchived") or item.get("archived") or False),
        "disabled": bool(item.get("isDisabled") or item.get("disabled") or False),
        "fork": bool(item.get("isFork") or item.get("fork") or False),
        "private": bool(item.get("isPrivate") or item.get("private") or False),
        "visibility": item.get("visibility") or ("private" if item.get("private") else "public"),
        "updated_at": item.get("updatedAt") or item.get("updated_at") or "",
        "pushed_at": item.get("pushedAt") or item.get("pushed_at") or "",
        "created_at": item.get("createdAt") or item.get("created_at") or "",
        "homepage": item.get("homepage") or item.get("homepageUrl") or "",
        "default_branch": item.get("defaultBranch") or item.get("default_branch") or "",
        "topics": [],
        "matched_queries": [],
        "query_purposes": {},
        "source": "search",
    }


def safe_int(value: Any, default: int = 0) -> int:
    """Convert gh/API scalar or connection-style count objects to int."""
    if value is None:
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    if isinstance(value, dict):
        for key in ("totalCount", "count", "value"):
            if key in value:
                return safe_int(value.get(key), default)
    return default


def normalize_repo_view(data: dict[str, Any]) -> dict[str, Any]:
    primary = data.get("primaryLanguage") or {}
    if isinstance(primary, dict):
        language = primary.get("name") or ""
    else:
        language = primary or ""
    lic = data.get("licenseInfo") or {}
    topics_obj = data.get("repositoryTopics") or []
    topics: list[str] = []
    if isinstance(topics_obj, list):
        for t in topics_obj:
            if isinstance(t, dict):
                topic = t.get("name") or (t.get("topic") or {}).get("name")
                if topic:
                    topics.append(str(topic))
            elif t:
                topics.append(str(t))
    branch = data.get("defaultBranchRef") or {}
    issues = data.get("issues") or {}
    return {
        "full_name": data.get("nameWithOwner"),
        "description": data.get("description") or "",
        "url": data.get("url"),
        "stars": safe_int(data.get("stargazerCount")),
        "forks": safe_int(data.get("forkCount")),
        "watchers": safe_int(data.get("watchers")),
        "open_issues": safe_int(issues),
        "language": language,
        "license": lic.get("spdxId") or lic.get("name") or "" if isinstance(lic, dict) else "",
        "archived": bool(data.get("isArchived") or False),
        "fork": bool(data.get("isFork") or False),
        "private": bool(data.get("isPrivate") or False),
        "updated_at": data.get("updatedAt") or "",
        "pushed_at": data.get("pushedAt") or "",
        "created_at": data.get("createdAt") or "",
        "homepage": data.get("homepageUrl") or "",
        "default_branch": branch.get("name") if isinstance(branch, dict) else "",
        "topics": topics,
    }


def gh_search(query: dict[str, str], *, args: argparse.Namespace, env: dict[str, str], errors: Path) -> list[dict[str, Any]]:
    fields = ",".join(SEARCH_FIELDS)
    try:
        query_terms = shlex.split(query["query"])
    except ValueError as exc:
        append_jsonl(errors, {"ts": utc_now(), "stage": "query_parse", "query_id": query["id"], "error": str(exc)})
        query_terms = [query["query"]]
    if not query_terms:
        return []
    gh_args = [
        "search", "repos", *query_terms,
        "--limit", str(args.limit_per_query),
        "--json", fields,
        "--visibility=public",
        "--archived=false",
    ]
    if not args.include_forks:
        gh_args.append("--include-forks=false")
    if args.language and len(args.language) == 1:
        gh_args.extend(["--language", args.language[0]])
    if args.sort != "best-match":
        gh_args.extend(["--sort", args.sort])
    if args.min_stars:
        gh_args.extend(["--stars", f">={args.min_stars}"])
    try:
        data = run_gh_json(gh_args, env=env, timeout=args.timeout, label=f"gh search {query['id']}", retries=args.retries)
        if not isinstance(data, list):
            append_jsonl(errors, {"ts": utc_now(), "stage": "search", "query_id": query["id"], "error": "gh returned non-list"})
            return []
        return data
    except Exception as exc:  # noqa: BLE001
        append_jsonl(errors, {"ts": utc_now(), "stage": "search", "query_id": query["id"], "error": str(exc)})
        if args.gh_only:
            return []
        return http_search(query, args=args, env=env, errors=errors)


def http_search(query: dict[str, str], *, args: argparse.Namespace, env: dict[str, str], errors: Path) -> list[dict[str, Any]]:
    q = query["query"]
    if args.min_stars:
        q += f" stars:>={args.min_stars}"
    q += " is:public archived:false"
    if not args.include_forks:
        q += " fork:false"
    if args.language:
        for lang in args.language:
            q += f" language:{lang}"
    url = "https://api.github.com/search/repositories?" + urllib.parse.urlencode({
        "q": q,
        "per_page": min(args.limit_per_query, 100),
        "sort": args.sort if args.sort in {"stars", "forks", "updated"} else "",
    })
    # HTTP fallback intentionally uses unauthenticated REST. Authenticated calls should
    # go through gh CLI so secrets are never read or logged by this portable script.
    try:
        data = http_json(url, env=env, timeout=args.timeout, retries=args.retries)
        return data.get("items") or []
    except Exception as exc:  # noqa: BLE001
        append_jsonl(errors, {"ts": utc_now(), "stage": "http_search", "query_id": query["id"], "error": str(exc)})
        return []


def enrich_repo(repo: dict[str, Any], *, args: argparse.Namespace, env: dict[str, str], errors: Path) -> dict[str, Any]:
    full_name = repo["full_name"]
    if not full_name or not args.prefer_gh or shutil.which("gh") is None:
        return repo
    try:
        data = run_gh_json(
            ["repo", "view", full_name, "--json", ",".join(REPO_VIEW_FIELDS)],
            env=env,
            timeout=args.timeout,
            label=f"gh repo view {full_name}",
            retries=args.retries,
        )
        if isinstance(data, dict):
            view = normalize_repo_view(data)
            for key, val in view.items():
                if key == "full_name" or val not in (None, "", [], 0):
                    repo[key] = val
            repo["source"] = repo.get("source", "search") + "+repo_view"
    except Exception as exc:  # noqa: BLE001
        append_jsonl(errors, {"ts": utc_now(), "stage": "repo_view", "repo": full_name, "error": str(exc)})
    return repo


def fetch_readme(repo: dict[str, Any], *, args: argparse.Namespace, env: dict[str, str], repo_dir: Path, errors: Path) -> str | None:
    full_name = repo["full_name"]
    readme_path = repo_dir / "readme.md"
    meta_path = repo_dir / "readme.meta.json"
    if readme_path.exists() and not args.refresh_readme:
        return readme_path.read_text(encoding="utf-8", errors="replace")

    # gh api first. This normally uses the authenticated gh token without exposing it.
    if args.prefer_gh and shutil.which("gh"):
        try:
            data = run_gh_json(
                ["api", f"repos/{full_name}/readme"],
                env=env,
                timeout=args.timeout,
                label=f"gh api readme {full_name}",
                retries=args.retries,
            )
            if data and data.get("content"):
                text = base64.b64decode(data["content"].encode("utf-8"), validate=False).decode("utf-8", errors="replace")
                write_text(readme_path, text)
                write_json(meta_path, {"source": "gh api", "sha": data.get("sha"), "path": data.get("path"), "download_url": data.get("download_url")})
                return text
        except Exception as exc:  # noqa: BLE001
            append_jsonl(errors, {"ts": utc_now(), "stage": "readme_gh", "repo": full_name, "error": str(exc)})

    branch = repo.get("default_branch") or "main"
    for candidate_branch in [branch, "main", "master"]:
        for name in ["README.md", "README.MD", "README.rst", "README"]:
            raw_url = f"https://raw.githubusercontent.com/{full_name}/{candidate_branch}/{name}"
            try:
                text = http_text(raw_url, env=env, timeout=args.timeout, retries=args.retries)
                if text:
                    write_text(readme_path, text)
                    write_json(meta_path, {"source": "raw", "url": raw_url})
                    return text
            except Exception as exc:  # noqa: BLE001
                append_jsonl(errors, {"ts": utc_now(), "stage": "readme_raw", "repo": full_name, "url": raw_url, "error": str(exc)})
                continue
    write_json(meta_path, {"source": "none", "available": False})
    return None


def parse_iso(date_text: str) -> dt.datetime | None:
    if not date_text:
        return None
    try:
        return dt.datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        return None


def hard_filter(repos: list[dict[str, Any]], *, args: argparse.Namespace) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    updated_after = parse_iso(args.updated_after) if args.updated_after else None
    languages = {x.lower() for x in args.language or []}
    for repo in repos:
        if repo.get("private") or str(repo.get("visibility", "")).lower() == "private":
            continue
        if repo.get("archived") or repo.get("disabled"):
            continue
        if repo.get("stars", 0) < args.min_stars:
            continue
        if repo.get("fork") and not args.include_forks:
            continue
        if languages and str(repo.get("language") or "").lower() not in languages:
            continue
        if updated_after:
            updated = parse_iso(repo.get("pushed_at") or repo.get("updated_at") or "")
            if updated and updated < updated_after:
                continue
        out.append(repo)
    return out


def markdown_to_plain(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def first_paragraphs(readme: str, max_paragraphs: int = 3, max_chars: int = 800) -> list[str]:
    plain = markdown_to_plain(readme)
    paras = []
    for chunk in re.split(r"\n\s*\n", plain):
        chunk = chunk.strip(" #\n\t")
        if not chunk or len(chunk) < 30:
            continue
        if chunk.lower().startswith(("table of contents", "目录")):
            continue
        paras.append(chunk[:max_chars])
        if len(paras) >= max_paragraphs:
            break
    return paras


def extract_headings(readme: str, limit: int = 30) -> list[str]:
    headings = []
    for line in readme.splitlines():
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if m:
            text = re.sub(r"[#`*_\[\]()]", "", m.group(2)).strip()
            if text:
                headings.append(text[:120])
        if len(headings) >= limit:
            break
    return headings


def extract_keyword_snippets(readme: str, keywords: list[str], *, max_per_keyword: int = 2, radius: int = 140) -> dict[str, list[str]]:
    plain = markdown_to_plain(readme)
    low = plain.lower()
    hits: dict[str, list[str]] = {}
    for kw in keywords:
        kw_low = kw.lower()
        start = 0
        snippets: list[str] = []
        for _ in range(max_per_keyword):
            idx = low.find(kw_low, start)
            if idx < 0:
                break
            left = max(0, idx - radius)
            right = min(len(plain), idx + len(kw) + radius)
            snippet = re.sub(r"\s+", " ", plain[left:right]).strip()
            snippets.append(snippet)
            start = idx + len(kw_low)
        if snippets:
            hits[kw] = snippets
    return hits


def extract_section_snippets(readme: str, wanted: Iterable[str], max_chars: int = 900) -> dict[str, str]:
    lines = readme.splitlines()
    sections: dict[str, str] = {}
    current_title = None
    current: list[str] = []

    def flush() -> None:
        nonlocal current_title, current
        if current_title and current:
            body = markdown_to_plain("\n".join(current)).strip()
            if body:
                sections[current_title] = body[:max_chars]
        current_title = None
        current = []

    wanted_low = [w.lower() for w in wanted]
    for line in lines:
        m = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
        if m:
            flush()
            title = re.sub(r"[#`*_\[\]()]", "", m.group(2)).strip()
            if any(w in title.lower() for w in wanted_low):
                current_title = title[:80]
            continue
        if current_title and len("\n".join(current)) < max_chars * 2:
            current.append(line)
    flush()
    return sections


def evidence_from_readme(repo: dict[str, Any], readme: str | None, keywords: list[str]) -> dict[str, Any]:
    if not readme:
        return {
            "repo": repo["full_name"],
            "available": False,
            "readme_chars": 0,
            "headings": [],
            "first_paragraphs": [],
            "keyword_hits": {},
            "install_signals": [],
            "docs_signals": [],
            "section_snippets": {},
        }
    low = readme.lower()
    keyword_hits = extract_keyword_snippets(readme, keywords)
    return {
        "repo": repo["full_name"],
        "available": True,
        "readme_chars": len(readme),
        "headings": extract_headings(readme),
        "first_paragraphs": first_paragraphs(readme),
        "keyword_hits": keyword_hits,
        "install_signals": [kw for kw in INSTALL_KEYWORDS if kw in low],
        "docs_signals": [kw for kw in DOC_KEYWORDS if kw in low],
        "section_snippets": extract_section_snippets(readme, ["feature", "quick", "install", "getting started", "usage", "demo", "example", "start"]),
    }


def recency_score(repo: dict[str, Any]) -> float:
    updated = parse_iso(repo.get("pushed_at") or repo.get("updated_at") or "")
    if not updated:
        return 0.3
    now = dt.datetime.now(dt.timezone.utc)
    days = max(0, (now - updated).days)
    if days <= 30:
        return 1.0
    if days <= 180:
        return 0.85
    if days <= 365:
        return 0.65
    if days <= 730:
        return 0.4
    return 0.2


def score_repo(repo: dict[str, Any], ev: dict[str, Any]) -> dict[str, Any]:
    stars_log = min(1.0, math.log10(max(1, repo.get("stars", 0))) / 5.0)
    fresh = recency_score(repo)
    readme_quality = 0.0
    if ev.get("available"):
        readme_quality += 0.25
        readme_quality += min(0.25, len(ev.get("headings") or []) / 40)
        readme_quality += min(0.20, len(ev.get("first_paragraphs") or []) * 0.08)
        readme_quality += min(0.15, len(ev.get("install_signals") or []) * 0.05)
        readme_quality += min(0.15, len(ev.get("docs_signals") or []) * 0.04)
    kw_count = len(ev.get("keyword_hits") or {})
    keyword_relevance = min(1.0, kw_count / 8.0)
    topic_text = " ".join(repo.get("topics") or []).lower()
    topic_match = 0.0
    if topic_text:
        topic_match = min(1.0, sum(1 for kw in DEFAULT_KEYWORDS if kw.lower() in topic_text) / 5.0)
    query_hit_score = min(1.0, len(repo.get("matched_queries") or []) / 3.0)
    base = (
        stars_log * 0.10
        + fresh * 0.15
        + readme_quality * 0.20
        + keyword_relevance * 0.30
        + topic_match * 0.10
        + query_hit_score * 0.15
    )
    return {
        "stars_log": round(stars_log, 4),
        "freshness_score": round(fresh, 4),
        "readme_score": round(readme_quality, 4),
        "keyword_relevance": round(keyword_relevance, 4),
        "topic_match": round(topic_match, 4),
        "query_hit_score": round(query_hit_score, 4),
        "base_score": round(base, 4),
    }


def brief_repo_md(candidate: dict[str, Any], index: int, max_snippets: int = 5) -> str:
    repo = candidate["repo"]
    ev = candidate["readme"]
    heur = candidate["heuristic"]
    lines = [
        f"## Candidate {index}: {repo['full_name']}",
        "",
        f"- URL: {repo.get('url') or 'n/a'}",
        f"- Stars: {repo.get('stars', 0):,} | Forks: {repo.get('forks', 0):,} | Open issues: {repo.get('open_issues', 0):,}",
        f"- Language: {repo.get('language') or 'n/a'} | License: {repo.get('license') or 'n/a'}",
        f"- Updated: {repo.get('updated_at') or 'n/a'} | Pushed: {repo.get('pushed_at') or 'n/a'}",
        f"- Topics: {', '.join(repo.get('topics') or []) or 'n/a'}",
        f"- Matched queries: {', '.join(repo.get('matched_queries') or []) or 'n/a'}",
        f"- Description: {repo.get('description') or 'n/a'}",
        f"- Script heuristic score: {heur.get('base_score')} (keyword={heur.get('keyword_relevance')}, readme={heur.get('readme_score')}, freshness={heur.get('freshness_score')})",
        f"- README chars: {ev.get('readme_chars', 0)} | install signals: {', '.join(ev.get('install_signals') or []) or 'n/a'} | docs signals: {', '.join(ev.get('docs_signals') or []) or 'n/a'}",
        f"- README headings: {', '.join((ev.get('headings') or [])[:10]) or 'n/a'}",
    ]
    if ev.get("first_paragraphs"):
        lines.append("- README first paragraphs:")
        for para in ev["first_paragraphs"][:2]:
            lines.append("  > " + para.replace("\n", " ")[:500])
    snippets = []
    for keyword, vals in (ev.get("keyword_hits") or {}).items():
        for snip in vals:
            snippets.append((keyword, snip))
    if snippets:
        lines.append("- Evidence snippets:")
        for keyword, snippet in snippets[:max_snippets]:
            lines.append(f"  - `{keyword}`: {snippet[:420]}")
    lines.append("")
    return "\n".join(lines)


def render_ai_brief(path: Path, *, topic: str, queries: list[dict[str, str]], manifest: dict[str, Any], candidates: list[dict[str, Any]], top_k: int) -> None:
    lines = [
        "# GitHub Repo Search Brief",
        "",
        f"检索主题：{topic}",
        f"检索时间：{manifest['started_at']}",
        "",
        "## Queries",
        "",
    ]
    for q in queries:
        lines.append(f"- `{q['id']}`: {q['query']} — {q.get('purpose') or ''}")
    lines.extend([
        "",
        "## Run summary",
        "",
        f"- 原始召回：{manifest.get('raw_count', 0)}",
        f"- 去重后：{manifest.get('deduped_count', 0)}",
        f"- 硬过滤后：{manifest.get('filtered_count', 0)}",
        f"- 进入 AI 评审：{min(top_k, len(candidates))}",
        f"- gh 可用：{manifest.get('gh_available')} | prefer gh: {manifest.get('prefer_gh')}",
        f"- Rate limit: `{manifest.get('rate_limit_summary', 'n/a')}`",
        "",
        "## How to use this brief",
        "",
        "脚本分数只是机械预筛，不是最终推荐结论。AI 应用用户场景重排，必要时只深读 Top 3-5 的缓存 README。",
        "",
    ])
    for i, cand in enumerate(candidates[:top_k], 1):
        lines.append(brief_repo_md(cand, i))
    write_text(path, "\n".join(lines))


def render_candidates_md(path: Path, candidates: list[dict[str, Any]]) -> None:
    lines = [
        "# GitHub Repo Candidates",
        "",
        "| # | Repo | Stars | Score | Language | License | Updated | Matched queries | Description |",
        "|---:|---|---:|---:|---|---|---|---|---|",
    ]
    for i, cand in enumerate(candidates, 1):
        repo = cand["repo"]
        desc = (repo.get("description") or "").replace("|", "\\|")[:160]
        lines.append(
            f"| {i} | [{repo['full_name']}]({repo.get('url')}) | {repo.get('stars',0)} | {cand['heuristic'].get('base_score')} | "
            f"{repo.get('language') or ''} | {repo.get('license') or ''} | {repo.get('updated_at') or ''} | "
            f"{', '.join(repo.get('matched_queries') or [])} | {desc} |"
        )
    write_text(path, "\n".join(lines) + "\n")


def rate_limit_summary(args: argparse.Namespace, env: dict[str, str]) -> str:
    if not args.prefer_gh or not shutil.which("gh"):
        return "gh unavailable or disabled"
    try:
        data = run_gh_json(["api", "rate_limit"], env=env, timeout=args.timeout, label="gh api rate_limit", retries=1)
        res = data.get("resources", {}) if isinstance(data, dict) else {}
        core = res.get("core", {})
        search = res.get("search", {})
        return f"core {core.get('remaining')}/{core.get('limit')}, search {search.get('remaining')}/{search.get('limit')}"
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {str(exc)[:120]}"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scripted GitHub repo search pipeline for AI-assisted recommendation reports.")
    p.add_argument("--queries", help="JSON file with {topic,constraints,queries[]} or a list of query strings/objects")
    p.add_argument("--query", action="append", help="Search query; can be repeated")
    p.add_argument("--topic", help="Topic name used in manifest and ai brief")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument("--limit-per-query", type=int, default=30)
    p.add_argument("--min-stars", type=int, default=100)
    p.add_argument("--top-k", type=int, default=40, help="Number of candidates in ai-input-topK.md")
    p.add_argument("--readme-top-n", type=int, default=40, help="Fetch README for top N filtered repos")
    p.add_argument("--metadata-top-n", type=int, default=80, help="Enrich metadata/topics for top N filtered repos")
    p.add_argument("--sort", default="best-match", choices=["best-match", "stars", "forks", "updated"])
    p.add_argument("--language", action="append", help="Optional language filter; can repeat")
    p.add_argument("--updated-after", help="Optional ISO date filter, e.g. 2024-01-01")
    p.add_argument("--include-forks", action="store_true")
    p.add_argument("--keywords", help="Comma-separated extra/override keywords for README evidence extraction")
    p.add_argument("--proxy", default=None, help=f"HTTP/HTTPS proxy; default env or {DEFAULT_PROXY}")
    p.add_argument("--no-proxy", action="store_true")
    p.add_argument("--set-all-proxy", action="store_true", help="Also set ALL_PROXY to the same proxy")
    p.add_argument("--prefer-gh", dest="prefer_gh", action="store_true", default=True)
    p.add_argument("--no-gh", dest="prefer_gh", action="store_false")
    p.add_argument("--gh-only", action="store_true", help="Do not fallback to HTTP search if gh search fails")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--refresh-readme", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    started = utc_now()
    env = setup_env(args)
    out = Path(args.out).expanduser().resolve()
    raw_dir = out / "raw"
    repo_root = out / "repos"
    mkdir(raw_dir)
    mkdir(repo_root)
    errors = out / "errors.jsonl"
    if errors.exists():
        errors.unlink()

    topic, constraints, queries = load_queries(args)
    write_json(out / "queries.json", {"topic": topic, "constraints": constraints, "queries": queries})

    gh_available = shutil.which("gh") is not None
    all_raw: list[dict[str, Any]] = []
    dedup: dict[str, dict[str, Any]] = {}

    for query in queries:
        raw = gh_search(query, args=args, env=env, errors=errors) if args.prefer_gh and gh_available else http_search(query, args=args, env=env, errors=errors)
        write_json(raw_dir / f"search-{query['id']}.json", raw)
        all_raw.extend(raw)
        for item in raw:
            repo = normalize_repo_from_search(item)
            full_name = repo.get("full_name")
            if not full_name:
                continue
            existing = dedup.get(full_name)
            if existing:
                if repo.get("stars", 0) > existing.get("stars", 0):
                    repo["matched_queries"] = existing.get("matched_queries", [])
                    repo["query_purposes"] = existing.get("query_purposes", {})
                    existing = repo
                    dedup[full_name] = existing
                existing.setdefault("matched_queries", []).append(query["id"])
                existing.setdefault("query_purposes", {})[query["id"]] = query.get("purpose")
            else:
                repo["matched_queries"] = [query["id"]]
                repo["query_purposes"] = {query["id"]: query.get("purpose")}
                dedup[full_name] = repo

    repos = list(dedup.values())
    repos.sort(key=lambda r: (len(r.get("matched_queries") or []), r.get("stars", 0)), reverse=True)
    write_json(out / "repos.json", repos)

    filtered = hard_filter(repos, args=args)
    filtered.sort(key=lambda r: (len(r.get("matched_queries") or []), r.get("stars", 0)), reverse=True)

    # Enrich the top slice before evidence/score; keep errors non-fatal.
    for i, repo in enumerate(filtered[: max(args.metadata_top_n, args.readme_top_n, args.top_k)]):
        filtered[i] = enrich_repo(repo, args=args, env=env, errors=errors)
    write_json(out / "repos.filtered.json", filtered)

    keywords = [k.strip() for k in (args.keywords.split(",") if args.keywords else DEFAULT_KEYWORDS) if k.strip()]
    candidates: list[dict[str, Any]] = []
    evidence_jsonl = out / "evidence.jsonl"
    if evidence_jsonl.exists():
        evidence_jsonl.unlink()
    for i, repo in enumerate(filtered):
        repo_dir = repo_root / safe_repo_dir(repo["full_name"])
        mkdir(repo_dir)
        write_json(repo_dir / "metadata.json", repo)
        readme = None
        if i < args.readme_top_n:
            readme = fetch_readme(repo, args=args, env=env, repo_dir=repo_dir, errors=errors)
        ev = evidence_from_readme(repo, readme, keywords)
        write_json(repo_dir / "evidence.json", ev)
        append_jsonl(evidence_jsonl, ev)
        cand = {"repo": repo, "readme": ev, "heuristic": score_repo(repo, ev)}
        candidates.append(cand)

    candidates.sort(key=lambda c: (c["heuristic"].get("base_score", 0), c["repo"].get("stars", 0)), reverse=True)
    write_json(out / "candidates.compact.json", candidates)
    with (out / "candidates.jsonl").open("w", encoding="utf-8") as f:
        for cand in candidates:
            f.write(json.dumps(cand, ensure_ascii=False, sort_keys=True) + "\n")
    render_candidates_md(out / "candidates.md", candidates)

    manifest = {
        "started_at": started,
        "finished_at": utc_now(),
        "topic": topic,
        "constraints": constraints,
        "args": {k: v for k, v in vars(args).items() if k not in {"proxy"}},
        "proxy_used": None if args.no_proxy else (args.proxy or env.get("HTTPS_PROXY") or env.get("HTTP_PROXY") or DEFAULT_PROXY),
        "gh_available": gh_available,
        "prefer_gh": args.prefer_gh,
        "raw_count": len(all_raw),
        "deduped_count": len(repos),
        "filtered_count": len(filtered),
        "candidate_count": len(candidates),
        "rate_limit_summary": rate_limit_summary(args, env),
    }
    write_json(out / "manifest.json", manifest)
    render_ai_brief(out / f"ai-input-top{args.top_k}.md", topic=topic, queries=queries, manifest=manifest, candidates=candidates, top_k=args.top_k)
    render_ai_brief(out / "ai-brief.md", topic=topic, queries=queries, manifest=manifest, candidates=candidates, top_k=args.top_k)

    print(json.dumps({
        "out": str(out),
        "raw_count": manifest["raw_count"],
        "deduped_count": manifest["deduped_count"],
        "filtered_count": manifest["filtered_count"],
        "candidate_count": manifest["candidate_count"],
        "ai_brief": str(out / "ai-brief.md"),
        "errors": str(errors) if errors.exists() else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
