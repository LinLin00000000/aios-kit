#!/usr/bin/env python3
"""Create compact, read-only AI-agent cost snapshots and comparable deltas.

The source ledgers are opened with SQLite ``mode=ro`` plus ``query_only``.
Snapshot output contains aggregates and fixed metadata only: no session IDs,
message/tool bodies, prompts, titles, provider endpoints, or secret values.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SNAPSHOT_SCHEMA = "aios.agent-cost.snapshot.v1"
DELTA_SCHEMA = "aios.agent-cost.delta.v1"
RECEIPT_SCHEMA = "aios.agent-cost.file-receipt.v1"
BILLABLE_FIELDS = (
    "input_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "output_tokens",
)
TOKEN_FIELDS = (*BILLABLE_FIELDS, "reasoning_tokens")
FOCUS_TOOLS = ("session_search", "read_file", "search_files", "terminal", "skill_view")
REVIEW_NARROW_REGEX = (
    r"(?i)(?:\b(?:review(?:er|ing)?|audit(?:or|ing)?|validat(?:e|ed|es|ion|or)?|"
    r"verif(?:y|ied|ication)|critic(?:ize|al|ique|ism)?)\b|"
    r"审查|审核|评审|复核|审计|验证|校验)"
)
REVIEW_WIDE_REGEX = (
    r"(?i)(?:\b(?:review(?:er|ing)?|audit(?:or|ing)?|validat(?:e|ed|es|ion|or)?|"
    r"verif(?:y|ied|ication)|check(?:ed|ing)?|inspect(?:ed|ion)?|"
    r"critic(?:ize|al|ique|ism)?|test(?:ed|ing)?|quality|security|safety|"
    r"proof|gate|red[- ]?team)\b|"
    r"审查|审核|评审|复核|审计|验证|校验|检查|检视|测试|质量|安全|验收|红队)"
)
REVIEW_NARROW = re.compile(REVIEW_NARROW_REGEX)
REVIEW_WIDE = re.compile(REVIEW_WIDE_REGEX)


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def int0(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def pct(numerator: int | float, denominator: int | float) -> float:
    return round((float(numerator) * 100.0 / float(denominator)), 6) if denominator else 0.0


def billable(bucket: dict[str, Any]) -> int:
    return sum(int0(bucket.get(field)) for field in BILLABLE_FIELDS)


def add_bucket(target: dict[str, int], source: dict[str, Any]) -> None:
    for field in TOKEN_FIELDS:
        target[field] = target.get(field, 0) + int0(source.get(field))


def nearest_rank(values: Iterable[int], percentile: float) -> int | None:
    ordered = sorted(int(value) for value in values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def distribution(values: Iterable[int]) -> dict[str, int | None]:
    materialized = [int(value) for value in values]
    return {
        "max": max(materialized) if materialized else None,
        "n": len(materialized),
        "p50": nearest_rank(materialized, 0.50),
        "p95": nearest_rank(materialized, 0.95),
        "total": sum(materialized),
    }


def parse_as_of(value: str | None) -> dt.datetime:
    if value is None:
        return dt.datetime.now(dt.UTC).replace(microsecond=0)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(f"invalid --as-of timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise SystemExit("--as-of must include a timezone offset or Z")
    return parsed.astimezone(dt.UTC)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def epoch_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    else:
        text = str(value).strip()
        try:
            numeric = float(text)
        except ValueError:
            normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
            try:
                parsed = dt.datetime.fromisoformat(normalized)
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.UTC)
            return parsed.timestamp()
    if abs(numeric) >= 100_000_000_000:
        numeric /= 1000.0
    return numeric


def in_window(value: Any, start: float, end: float) -> bool:
    observed = epoch_seconds(value)
    return observed is not None and start <= observed <= end


def connect_read_only(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise SystemExit(f"SQLite source not found: {path}")
    encoded = urllib.parse.quote(str(path.resolve()), safe="/")
    connection = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def require_columns(connection: sqlite3.Connection, table: str, required: set[str]) -> set[str]:
    columns = table_columns(connection, table)
    missing = sorted(required - columns)
    if missing:
        raise SystemExit(f"{table} is missing required columns: {', '.join(missing)}")
    return columns


def rows_for_ids(
    connection: sqlite3.Connection,
    sql_prefix: str,
    ids: list[str],
    *,
    chunk_size: int = 500,
) -> Iterable[sqlite3.Row]:
    for offset in range(0, len(ids), chunk_size):
        chunk = ids[offset : offset + chunk_size]
        placeholders = ",".join("?" for _ in chunk)
        yield from connection.execute(f"{sql_prefix} ({placeholders})", chunk)


def root_for(session_id: str, parents: dict[str, str | None]) -> str:
    current = session_id
    seen: set[str] = set()
    while current not in seen:
        seen.add(current)
        parent = parents.get(current)
        if not parent:
            return current
        if parent not in parents:
            return parent
        current = parent
    return min(seen)


def review_first_messages(
    connection: sqlite3.Connection,
    session_ids: list[str],
) -> dict[str, str]:
    if not session_ids:
        return {}
    columns = require_columns(connection, "messages", {"id", "session_id", "role", "content"})
    active_clause = " AND active=1" if "active" in columns else ""
    order_field = "timestamp" if "timestamp" in columns else "id"
    sql = (
        f"SELECT id,session_id,content,{order_field} AS observed_order "
        "FROM messages WHERE role='user'"
        f"{active_clause} AND session_id IN"
    )
    first: dict[str, str] = {}
    rows = list(rows_for_ids(connection, sql, sorted(session_ids)))
    rows.sort(
        key=lambda row: (
            str(row["session_id"]),
            epoch_seconds(row["observed_order"]) or 0,
            int0(row["id"]),
        )
    )
    for row in rows:
        first.setdefault(str(row["session_id"]), str(row["content"] or ""))
    return first


def hermes_metrics(
    connection: sqlite3.Connection,
    start: float,
    end: float,
    subagent_threshold: float,
    review_threshold: float,
) -> dict[str, Any]:
    session_required = {
        "id", "source", "parent_session_id", "started_at", "api_call_count", *TOKEN_FIELDS
    }
    require_columns(connection, "sessions", session_required)
    all_sessions = [dict(row) for row in connection.execute(
        "SELECT id,source,parent_session_id,started_at,api_call_count,"
        "input_tokens,cache_read_tokens,cache_write_tokens,output_tokens,reasoning_tokens FROM sessions"
    )]
    parents = {
        str(row["id"]): str(row["parent_session_id"]) if row.get("parent_session_id") else None
        for row in all_sessions
    }
    sessions = [row for row in all_sessions if in_window(row.get("started_at"), start, end)]
    session_ids = [str(row["id"]) for row in sessions]
    usage_by_session: dict[str, dict[str, int]] = defaultdict(
        lambda: {**{field: 0 for field in TOKEN_FIELDS}, "api_call_count": 0, "rows": 0}
    )
    usage_rows = 0
    if session_ids:
        require_columns(
            connection,
            "session_model_usage",
            {"session_id", "api_call_count", *TOKEN_FIELDS},
        )
        sql = (
            "SELECT session_id,api_call_count,input_tokens,cache_read_tokens,cache_write_tokens,"
            "output_tokens,reasoning_tokens FROM session_model_usage WHERE session_id IN"
        )
        for row in rows_for_ids(connection, sql, sorted(session_ids)):
            session_id = str(row["session_id"])
            bucket = usage_by_session[session_id]
            for field in TOKEN_FIELDS:
                bucket[field] += int0(row[field])
            bucket["api_call_count"] += int0(row["api_call_count"])
            bucket["rows"] += 1
            usage_rows += 1

    canonical_by_session: dict[str, dict[str, int]] = {}
    direct_reasoning = 0
    attributed_reasoning = 0
    positive_residual_sessions = 0
    usage_exceeds_session_buckets = 0
    for session in sessions:
        session_id = str(session["id"])
        usage = usage_by_session[session_id]
        canonical = {field: 0 for field in TOKEN_FIELDS}
        had_residual = False
        for field in BILLABLE_FIELDS:
            direct_value = int0(session.get(field))
            usage_value = int0(usage.get(field))
            residual = max(0, direct_value - usage_value)
            canonical[field] = usage_value + residual
            had_residual = had_residual or residual > 0
            usage_exceeds_session_buckets += usage_value > direct_value
        direct_reasoning += int0(session.get("reasoning_tokens"))
        attributed_reasoning += int0(usage.get("reasoning_tokens"))
        canonical["reasoning_tokens"] = int0(usage.get("reasoning_tokens"))
        direct_calls = int0(session.get("api_call_count"))
        usage_calls = int0(usage.get("api_call_count"))
        canonical["api_call_count"] = usage_calls + max(0, direct_calls - usage_calls)
        had_residual = had_residual or direct_calls > usage_calls
        positive_residual_sessions += had_residual
        canonical_by_session[session_id] = canonical

    totals = {field: 0 for field in TOKEN_FIELDS}
    canonical_api_calls = 0
    roots: dict[str, dict[str, int]] = defaultdict(lambda: {"api_calls": 0, "cache_read_tokens": 0})
    subagent_ids: list[str] = []
    subagent_tokens = 0
    for session in sessions:
        session_id = str(session["id"])
        canonical = canonical_by_session[session_id]
        add_bucket(totals, canonical)
        canonical_api_calls += canonical["api_call_count"]
        root = roots[root_for(session_id, parents)]
        root["api_calls"] += canonical["api_call_count"]
        root["cache_read_tokens"] += canonical["cache_read_tokens"]
        if str(session.get("source") or "") == "subagent":
            subagent_ids.append(session_id)
            subagent_tokens += billable(canonical)

    canonical_billable = billable(totals)
    first_messages = review_first_messages(connection, subagent_ids)

    def review_group(pattern: re.Pattern[str]) -> dict[str, Any]:
        matched = [session_id for session_id in subagent_ids if pattern.search(first_messages.get(session_id, ""))]
        tokens = sum(billable(canonical_by_session[session_id]) for session_id in matched)
        share = pct(tokens, canonical_billable)
        return {
            "billable_token_volume": tokens,
            "over_threshold": share > review_threshold,
            "sessions": len(matched),
            "share_pct": share,
            "threshold_pct": review_threshold,
        }

    subagent_share = pct(subagent_tokens, canonical_billable)
    return {
        "reconciliation": {
            "api_calls": canonical_api_calls,
            "billable_buckets": {field: totals[field] for field in BILLABLE_FIELDS},
            "billable_token_volume": canonical_billable,
            "four_bucket_sum_matches": canonical_billable == sum(totals[field] for field in BILLABLE_FIELDS),
            "positive_residual_sessions": positive_residual_sessions,
            "reasoning_counted_as_extra_billable": False,
            "reasoning_tokens": {
                "direct_session_projection": direct_reasoning,
                "model_usage_attributed": attributed_reasoning,
                "rule": "reasoning is an output subset and is never added to the four billable buckets",
            },
            "session_model_usage_rows": usage_rows,
            "usage_exceeds_session_bucket_count": usage_exceeds_session_buckets,
        },
        "root_signal": {
            "api_calls": distribution(root["api_calls"] for root in roots.values()),
            "cache_read_tokens": distribution(root["cache_read_tokens"] for root in roots.values()),
            "roots": len(roots),
        },
        "subagent_signal": {
            "billable_token_volume": subagent_tokens,
            "over_threshold": subagent_share > subagent_threshold,
            "sessions": len(subagent_ids),
            "share_pct": subagent_share,
            "threshold_pct": subagent_threshold,
        },
        "review_signal": {
            "classification": "heuristic; first user task text is matched in memory and never emitted",
            "narrow": review_group(REVIEW_NARROW),
            "wide": review_group(REVIEW_WIDE),
        },
        "rows": {"sessions": len(sessions)},
    }


def studio_metrics(
    connection: sqlite3.Connection,
    start: float,
    end: float,
    long_context_threshold: int,
) -> dict[str, Any]:
    require_columns(
        connection,
        "session_usage",
        {
            "id", "session_id", "created_at", "usage_scope", "api_calls",
            "input_tokens", "cache_read_tokens", "cache_write_tokens",
        },
    )
    calls: list[dict[str, Any]] = []
    for row in connection.execute(
        "SELECT id,session_id,created_at,api_calls,input_tokens,cache_read_tokens,"
        "cache_write_tokens FROM session_usage WHERE usage_scope='model_call' ORDER BY created_at,id"
    ):
        if not in_window(row["created_at"], start, end):
            continue
        calls.append(
            {
                "id": int0(row["id"]),
                "session_id": str(row["session_id"]),
                "created_at": epoch_seconds(row["created_at"]) or 0,
                "api_calls": max(1, int0(row["api_calls"])),
                "prompt_tokens": (
                    int0(row["input_tokens"])
                    + int0(row["cache_read_tokens"])
                    + int0(row["cache_write_tokens"])
                ),
            }
        )
    first: dict[str, dict[str, Any]] = {}
    for call in sorted(calls, key=lambda item: (item["created_at"], item["id"])):
        first.setdefault(call["session_id"], call)
    model_calls = sum(call["api_calls"] for call in calls)
    long_calls = sum(
        call["api_calls"] for call in calls if call["prompt_tokens"] > long_context_threshold
    )

    require_columns(connection, "messages", {"role", "content", "tool_name", "timestamp"})
    all_payload_sizes: list[int] = []
    focus_payload_sizes: dict[str, list[int]] = {name: [] for name in FOCUS_TOOLS}
    # SQL returns only fixed metadata and UTF-8 byte lengths; body values never
    # cross the SQLite boundary into this process.
    for row in connection.execute(
        "SELECT tool_name,timestamp,LENGTH(CAST(COALESCE(content,'') AS BLOB)) AS payload_bytes "
        "FROM messages WHERE role='tool'"
    ):
        if not in_window(row["timestamp"], start, end):
            continue
        size = int0(row["payload_bytes"])
        all_payload_sizes.append(size)
        tool = str(row["tool_name"] or "")
        if tool in focus_payload_sizes:
            focus_payload_sizes[tool].append(size)

    return {
        "startup_signal": {
            "first_call_prompt_tokens": distribution(call["prompt_tokens"] for call in first.values()),
            "long_context_calls": long_calls,
            "long_context_share_pct": pct(long_calls, model_calls),
            "long_context_threshold_tokens": long_context_threshold,
            "model_call_rows": len(calls),
            "model_calls": model_calls,
            "sessions_with_model_calls": len(first),
        },
        "tool_signal": {
            "all_tools": distribution(all_payload_sizes),
            "focus_tools": {
                name: distribution(focus_payload_sizes[name]) for name in FOCUS_TOOLS
            },
            "payload_tokenizer_id": "utf8-bytes-v1",
            "unit": "bytes",
        },
    }


def build_snapshot(args: argparse.Namespace) -> dict[str, Any]:
    as_of = parse_as_of(args.as_of)
    if args.window_days <= 0:
        raise SystemExit("--window-days must be positive")
    if args.long_context_threshold <= 0:
        raise SystemExit("--long-context-threshold must be positive")
    start_at = as_of - dt.timedelta(days=args.window_days)
    start = start_at.timestamp()
    end = as_of.timestamp()
    hermes = connect_read_only(args.hermes_db)
    studio = connect_read_only(args.studio_db)
    try:
        hermes_result = hermes_metrics(
            hermes,
            start,
            end,
            args.subagent_threshold,
            args.review_threshold,
        )
        studio_result = studio_metrics(studio, start, end, args.long_context_threshold)
    finally:
        hermes.close()
        studio.close()

    return {
        "generated_at": iso_z(as_of),
        "metadata": {
            "payload_tokenizer": {
                "fixed_for_comparability": True,
                "id": "utf8-bytes-v1",
                "method": "SQLite UTF-8 BLOB byte length; payload bodies are not selected",
                "unit": "bytes",
            },
            "percentile_method": "nearest-rank",
            "review_regex": {
                "classification": "heuristic",
                "narrow": REVIEW_NARROW_REGEX,
                "wide": REVIEW_WIDE_REGEX,
            },
            "thresholds": {
                "long_context_prompt_tokens": args.long_context_threshold,
                "review_like_billable_share_pct": args.review_threshold,
                "subagent_billable_share_pct": args.subagent_threshold,
            },
        },
        "ok": True,
        "privacy": {
            "database_paths_emitted": False,
            "message_or_tool_bodies_emitted": False,
            "provider_endpoint_fields_selected": False,
            "review_classification_reads_first_user_text_in_memory": True,
            "secret_values_emitted": False,
            "session_ids_emitted": False,
            "tool_payload_bodies_selected": False,
        },
        "reconciliation": hermes_result["reconciliation"],
        "schema": SNAPSHOT_SCHEMA,
        "signals": {
            "review_like_billable_share": hermes_result["review_signal"],
            "root_calls_cache_replay": hermes_result["root_signal"],
            "startup_and_long_context": studio_result["startup_signal"],
            "subagent_billable_share": hermes_result["subagent_signal"],
            "tool_result_tail": studio_result["tool_signal"],
        },
        "sources": {
            "canonical_ledger": "Hermes sessions plus per-session session_model_usage and positive residuals",
            "dedup_rule": "Hermes is canonical for billable buckets; overlapping Studio sessions/model_call rows are signal-only and never summed into it",
            "hermes_session_rows": hermes_result["rows"]["sessions"],
            "source_connections": "SQLite mode=ro, query_only transaction",
            "studio_usage_added_to_canonical_ledger": False,
        },
        "window": {
            "days": args.window_days,
            "end": iso_z(as_of),
            "start": iso_z(start_at),
            "timezone": "UTC",
        },
    }


def nested(document: dict[str, Any], *path: str) -> Any:
    value: Any = document
    for key in path:
        value = value[key]
    return value


def build_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    for label, document in (("before", before), ("after", after)):
        if document.get("schema") != SNAPSHOT_SCHEMA:
            raise SystemExit(f"{label} is not a {SNAPSHOT_SCHEMA} document")
    checks = {
        "canonical_ledger": before["sources"]["canonical_ledger"] == after["sources"]["canonical_ledger"],
        "payload_tokenizer": nested(before, "metadata", "payload_tokenizer", "id")
        == nested(after, "metadata", "payload_tokenizer", "id"),
        "percentile_method": before["metadata"]["percentile_method"]
        == after["metadata"]["percentile_method"],
        "review_regex": before["metadata"]["review_regex"] == after["metadata"]["review_regex"],
        "thresholds": before["metadata"]["thresholds"] == after["metadata"]["thresholds"],
        "window_days": before["window"]["days"] == after["window"]["days"],
    }
    if not all(checks.values()):
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise SystemExit(f"snapshots are not comparable: {failed}")
    metrics = {
        "canonical_billable_token_volume": ("reconciliation", "billable_token_volume"),
        "first_call_prompt_p50": ("signals", "startup_and_long_context", "first_call_prompt_tokens", "p50"),
        "long_context_share_pct": ("signals", "startup_and_long_context", "long_context_share_pct"),
        "review_like_narrow_share_pct": ("signals", "review_like_billable_share", "narrow", "share_pct"),
        "review_like_wide_share_pct": ("signals", "review_like_billable_share", "wide", "share_pct"),
        "root_api_calls_total": ("signals", "root_calls_cache_replay", "api_calls", "total"),
        "root_cache_read_tokens_total": ("signals", "root_calls_cache_replay", "cache_read_tokens", "total"),
        "subagent_billable_share_pct": ("signals", "subagent_billable_share", "share_pct"),
        "tool_result_max": ("signals", "tool_result_tail", "all_tools", "max"),
        "tool_result_p95": ("signals", "tool_result_tail", "all_tools", "p95"),
    }
    deltas: dict[str, int | float | None] = {}
    for name, path in metrics.items():
        old = nested(before, *path)
        new = nested(after, *path)
        deltas[name] = None if old is None or new is None else round(new - old, 6)
    return {
        "after": {"window_end": after["window"]["end"]},
        "before": {"window_end": before["window"]["end"]},
        "comparability": {"checks": checks, "comparable": True},
        "delta": deltas,
        "ok": True,
        "schema": DELTA_SCHEMA,
    }


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot read JSON document {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"JSON document must be an object: {path}")
    return value


def emit(document: dict[str, Any], output: Path | None, protected_inputs: Iterable[Path]) -> None:
    if output is None:
        print(compact_json(document))
        return
    output = output.expanduser()
    protected = {path.expanduser().resolve() for path in protected_inputs}
    if output.resolve() in protected:
        raise SystemExit("--output must not overwrite an input ledger or snapshot")
    output.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, output)
    receipt = {
        "bytes": len(data),
        "document_schema": document["schema"],
        "ok": True,
        "path": str(output),
        "schema": RECEIPT_SCHEMA,
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    print(compact_json(receipt))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot = subparsers.add_parser("snapshot", help="read two SQLite projections and emit five compact signals")
    snapshot.add_argument("--hermes-db", type=Path, default=Path.home() / ".hermes" / "state.db")
    snapshot.add_argument("--studio-db", type=Path, default=Path.home() / ".hermes-web-ui" / "hermes-web-ui.db")
    snapshot.add_argument("--as-of", help="inclusive ISO-8601 window end; defaults to current UTC time")
    snapshot.add_argument("--window-days", type=int, default=30)
    snapshot.add_argument("--subagent-threshold", type=float, default=25.0)
    snapshot.add_argument("--review-threshold", type=float, default=15.0)
    snapshot.add_argument("--long-context-threshold", type=int, default=272_000)
    snapshot.add_argument("--output", type=Path, help="write the full JSON document and print a compact receipt")

    delta = subparsers.add_parser("delta", help="compare two compatible snapshot JSON files")
    delta.add_argument("before", type=Path)
    delta.add_argument("after", type=Path)
    delta.add_argument("--output", type=Path, help="write the full JSON document and print a compact receipt")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.command == "snapshot":
            document = build_snapshot(args)
            emit(document, args.output, (args.hermes_db, args.studio_db))
        else:
            before = load_json_object(args.before)
            after = load_json_object(args.after)
            document = build_delta(before, after)
            emit(document, args.output, (args.before, args.after))
    except sqlite3.DatabaseError as exc:
        raise SystemExit(f"SQLite read failed: {exc}") from exc


if __name__ == "__main__":
    main()
