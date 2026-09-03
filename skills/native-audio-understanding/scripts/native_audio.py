#!/usr/bin/env python3
"""Send one local audio file through an explicitly selected model-input protocol."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
DEFAULT_MAX_BYTES = 12 * 1024 * 1024
DEFAULT_TIMEOUT = 180
PROTOCOLS = (
    "auto",
    "gemini-native-inline",
    "openai-chat-input-audio",
    "openai-chat-data-url",
)
AUTH_MODES = ("auto", "bearer", "x-goog-api-key", "none")
SUPPORTED_SUFFIXES = {
    ".mp3": "audio/mpeg",
    ".mp4": "audio/mp4",
    ".m4a": "audio/mp4",
    ".mpeg": "audio/mpeg",
    ".mpga": "audio/mpeg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}
SECRET_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "x-api-key",
    "api-key",
    "x-goog-api-key",
    "cookie",
    "set-cookie",
}
SECRET_JSON_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "secret",
    "password",
    "cookie",
    "set_cookie",
}
SECRET_PATH_NAMES = {
    ".env",
    "auth.json",
    "credentials.json",
    "secrets.json",
    "hosts.yml",
}
_BOOTSTRAP_ENV = "NATIVE_AUDIO_HERMES_BOOTSTRAPPED"


class NativeAudioError(RuntimeError):
    pass


def _redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in SECRET_JSON_KEYS:
                result[key] = "[REDACTED]"
            elif normalized == "data" and isinstance(item, str):
                # Error responses may echo a request. Treat every `data` value
                # as potentially binary; do not rely on a length threshold.
                result[key] = "[REDACTED_BINARY]"
            elif normalized in {"url", "image_url"} and isinstance(item, str) and item.startswith("data:"):
                result[key] = "[REDACTED_DATA_URL]"
            else:
                result[key] = _redact_json(item)
        return result
    if isinstance(value, list):
        return [_redact_json(item) for item in value]
    return value


def sanitized_error(value: Any) -> str:
    text = str(value or "")[:4000]
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        parsed = None
    if parsed is not None:
        text = json.dumps(_redact_json(parsed), ensure_ascii=False, separators=(",", ":"))
    text = re.sub(
        r'''(?i)(["'](?:api[_-]?key|token|access[_-]?token|refresh[_-]?token|authorization|secret|password|cookie)["']\s*:\s*["'])[^"']+(["'])''',
        r"\1[REDACTED]\2",
        text,
    )
    text = re.sub(
        r"(?i)(bearer\s+|api[_-]?key[=:\s]+|token[=:\s]+)[^\s,}\]]+",
        r"\1[REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)((?:x-goog-api-key|x-api-key|api-key|proxy-authorization|cookie))\s*[:=]\s*[^\s,}\]]+",
        r"\1: [REDACTED]",
        text,
    )
    text = re.sub(
        r"(?i)data:audio/[^,\s\"']+,[A-Za-z0-9+/=]+",
        "[REDACTED_AUDIO_DATA_URL]",
        text,
    )
    return text


def _hermes_python_candidates() -> list[Path]:
    homes: list[Path] = []
    explicit = os.environ.get("HERMES_HOME", "").strip()
    if explicit:
        configured = Path(explicit).expanduser()
        homes.append(configured)
        if configured.parent.name == "profiles":
            homes.append(configured.parent.parent)
    homes.append(Path.home() / ".hermes")

    candidates: list[Path] = []
    for home in homes:
        candidates.extend(
            [
                home / "hermes-agent" / "venv" / "bin" / "python",
                home / "hermes-agent" / "venv" / "Scripts" / "python.exe",
            ]
        )
    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _ensure_hermes_runtime_importable() -> None:
    try:
        import hermes_cli.runtime_provider  # noqa: F401
        return
    except ImportError:
        pass

    if os.environ.get(_BOOTSTRAP_ENV) == "1":
        raise NativeAudioError(
            "Hermes runtime modules are unavailable; use --runtime explicit or run with the Hermes Python runtime"
        )

    for candidate in _hermes_python_candidates():
        if not candidate.is_file():
            continue
        try:
            probe = subprocess.run(
                [str(candidate), "-c", "import hermes_cli.runtime_provider"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if probe.returncode != 0:
            continue
        env = os.environ.copy()
        env[_BOOTSTRAP_ENV] = "1"
        os.execve(str(candidate), [str(candidate), str(Path(__file__).resolve()), *sys.argv[1:]], env)
    raise NativeAudioError(
        "cannot locate an installed Hermes Python runtime; use --runtime explicit"
    )


def _validate_url(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise NativeAudioError("base URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise NativeAudioError("base URL must not contain embedded credentials")
    if parsed.query or parsed.fragment:
        raise NativeAudioError("base URL must not contain a query or fragment")
    return value


def _safe_runtime_headers(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        lowered = name.lower()
        if not name or lowered in {"host", "content-length", "connection"}:
            continue
        if "\r" in name or "\n" in name or "\r" in str(value) or "\n" in str(value):
            raise NativeAudioError("runtime Provider contains an invalid HTTP header")
        result[name] = str(value)
    return result


def resolve_runtime(args: argparse.Namespace) -> dict[str, Any]:
    if args.runtime == "explicit":
        if not args.base_url:
            raise NativeAudioError("--base-url is required with --runtime explicit")
        if not args.model:
            raise NativeAudioError("--model is required with --runtime explicit")
        api_key = ""
        if args.auth != "none":
            if not args.api_key_env:
                raise NativeAudioError(
                    "--api-key-env is required with explicit runtime unless --auth none is selected"
                )
            api_key = str(os.environ.get(args.api_key_env) or "").strip()
            if not api_key and not args.dry_run:
                raise NativeAudioError(f"environment variable {args.api_key_env} is not set")
        return {
            "provider": args.provider or "explicit",
            "requested_provider": args.provider or "explicit",
            "model": args.model,
            "base_url": _validate_url(args.base_url),
            "api_mode": "explicit",
            "api_key": api_key,
            "extra_headers": {},
            "credential_source": f"env:{args.api_key_env}" if args.api_key_env else "none",
        }

    _ensure_hermes_runtime_importable()
    try:
        from hermes_cli.runtime_provider import resolve_runtime_provider

        runtime = resolve_runtime_provider(
            requested=args.provider or None,
            target_model=args.model or None,
        )
    except Exception as exc:
        raise NativeAudioError(f"cannot resolve the active Hermes Provider: {sanitized_error(exc)}") from exc
    if not isinstance(runtime, dict):
        raise NativeAudioError("Hermes Provider resolver returned an invalid runtime descriptor")
    model = str(args.model or runtime.get("model") or "").strip()
    if not model:
        raise NativeAudioError("the active Hermes runtime did not resolve a model")
    base_url = _validate_url(str(runtime.get("base_url") or ""))
    api_key = str(runtime.get("api_key") or "").strip()
    if args.auth != "none" and not api_key and not args.dry_run:
        raise NativeAudioError("the active Hermes Provider did not resolve a usable credential")
    return {
        "provider": str(runtime.get("provider") or "").strip() or "unknown",
        "requested_provider": str(
            args.provider or runtime.get("requested_provider") or runtime.get("provider") or ""
        ).strip() or "unknown",
        "model": model,
        "base_url": base_url,
        "api_mode": str(runtime.get("api_mode") or "").strip() or "unknown",
        "api_key": api_key,
        "extra_headers": _safe_runtime_headers(runtime.get("extra_headers")),
        "credential_source": str(runtime.get("source") or "hermes-runtime"),
    }


def _looks_like_audio(data: bytes, suffix: str) -> bool:
    if suffix in {".m4a", ".mp4"}:
        return len(data) >= 12 and data[4:8] == b"ftyp"
    if suffix == ".wav":
        return data.startswith(b"RIFF") and data[8:12] == b"WAVE"
    if suffix in {".ogg", ".oga", ".opus"}:
        return data.startswith(b"OggS")
    if suffix == ".flac":
        return data.startswith(b"fLaC")
    if suffix == ".webm":
        return data.startswith(b"\x1a\x45\xdf\xa3")
    if suffix == ".mp3":
        return data.startswith(b"ID3") or (
            len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
        )
    if suffix in {".aac", ".mpeg", ".mpga"}:
        return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xF0) == 0xF0
    return False


def validate_audio_path(raw_path: str, max_bytes: int) -> tuple[Path, str, int]:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise NativeAudioError(f"audio file not found: {path}")
    lowered_parts = {part.lower() for part in path.parts}
    if path.name.lower() in SECRET_PATH_NAMES or "mcp-tokens" in lowered_parts:
        raise NativeAudioError("refusing to read a known credential or secret-store path")
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise NativeAudioError(
            f"unsupported audio extension {suffix or '<none>'}; choose one of: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    size = path.stat().st_size
    if size <= 0:
        raise NativeAudioError("audio file is empty")
    if size > max_bytes:
        raise NativeAudioError(
            f"audio file is {size} bytes; inline request limit is {max_bytes} bytes"
        )
    with path.open("rb") as source:
        head = source.read(32)
    if not _looks_like_audio(head, suffix):
        raise NativeAudioError("audio file magic bytes do not match its extension")
    # Use a small canonical MIME map instead of platform-dependent
    # mimetypes.guess_type() spellings such as audio/x-wav.
    mime = SUPPORTED_SUFFIXES[suffix]
    return path, mime, size


def resolve_protocol(requested: str, base_url: str) -> str:
    if requested != "auto":
        return requested
    parsed = urllib.parse.urlparse(base_url)
    host = (parsed.hostname or "").lower()
    normalized_path = parsed.path.rstrip("/").lower()
    if host == "generativelanguage.googleapis.com" and not normalized_path.endswith("/openai"):
        return "gemini-native-inline"
    raise NativeAudioError(
        "protocol auto-resolution is intentionally conservative; select a verified --protocol for this endpoint"
    )


def resolve_auth(requested: str, protocol: str) -> str:
    if requested != "auto":
        return requested
    return "x-goog-api-key" if protocol == "gemini-native-inline" else "bearer"


def _endpoint(base_url: str, model: str, protocol: str) -> str:
    if protocol == "gemini-native-inline":
        bare_model = model
        for prefix in ("google/", "gemini/"):
            if bare_model.lower().startswith(prefix):
                bare_model = bare_model[len(prefix):]
                break
        encoded_model = urllib.parse.quote(bare_model, safe="-._~")
        return f"{base_url}/models/{encoded_model}:generateContent"
    return f"{base_url}/chat/completions"


def _payload(protocol: str, model: str, prompt: str, encoded: str, mime: str, suffix: str) -> dict[str, Any]:
    if protocol == "gemini-native-inline":
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": mime, "data": encoded}},
                    ],
                }
            ]
        }
    if protocol == "openai-chat-input-audio":
        format_name = {".wav": "wav", ".mp3": "mp3"}.get(suffix)
        if not format_name:
            raise NativeAudioError(
                "openai-chat-input-audio supports only WAV or MP3; this helper does not transcode"
            )
        return {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": encoded, "format": format_name}},
                    ],
                }
            ],
        }
    if protocol == "openai-chat-data-url":
        return {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}"}},
                    ],
                }
            ],
        }
    raise NativeAudioError(f"unsupported protocol: {protocol}")


def _headers(runtime: dict[str, Any], auth_mode: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"native-audio-understanding/{VERSION}",
    }
    headers.update(runtime.get("extra_headers") or {})
    api_key = str(runtime.get("api_key") or "")
    if auth_mode == "bearer" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif auth_mode == "x-goog-api-key" and api_key:
        headers["x-goog-api-key"] = api_key
    return headers


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise NativeAudioError(
            f"Provider returned HTTP {exc.code}: {sanitized_error(body)}"
        ) from exc
    except urllib.error.URLError as exc:
        raise NativeAudioError(f"cannot reach Provider: {sanitized_error(exc.reason)}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise NativeAudioError(
            f"Provider returned invalid JSON: {sanitized_error(body)}"
        ) from exc
    if not isinstance(result, dict):
        raise NativeAudioError("Provider returned a non-object JSON response")
    return result


def _extract_text(response: dict[str, Any], protocol: str) -> str:
    if protocol == "gemini-native-inline":
        texts: list[str] = []
        for candidate in response.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            if not isinstance(content, dict):
                continue
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        return "\n".join(texts).strip()

    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for part in content:
            if not isinstance(part, dict):
                continue
            value = part.get("text") or part.get("content")
            if isinstance(value, str):
                texts.append(value)
        return "\n".join(texts).strip()
    return ""


def _public_runtime(runtime: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": runtime.get("requested_provider") or runtime.get("provider"),
        "resolved_provider": runtime.get("provider"),
        "model": runtime.get("model"),
        "api_mode": runtime.get("api_mode"),
        "base_url": runtime.get("base_url"),
        "credential_source": runtime.get("credential_source"),
    }


def run_send(args: argparse.Namespace) -> int:
    path, mime, size = validate_audio_path(args.audio, args.max_bytes)
    runtime = resolve_runtime(args)
    protocol = resolve_protocol(args.protocol, runtime["base_url"])
    auth_mode = resolve_auth(args.auth, protocol)
    endpoint = _endpoint(runtime["base_url"], runtime["model"], protocol)
    plan = {
        "success": True,
        "dry_run": True,
        "runtime": _public_runtime(runtime),
        "protocol": protocol,
        "auth": auth_mode,
        "endpoint": endpoint,
        "audio": {
            "path": str(path),
            "mime_type": mime,
            "bytes": size,
        },
        "prompt_present": bool(args.prompt),
        "request_sent": False,
    }
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    with path.open("rb") as source:
        encoded = base64.b64encode(source.read()).decode("ascii")
    payload = _payload(protocol, runtime["model"], args.prompt, encoded, mime, path.suffix.lower())
    response = _post_json(endpoint, _headers(runtime, auth_mode), payload, args.timeout)
    text = _extract_text(response, protocol)
    if not text:
        shape = sorted(str(key) for key in response.keys())
        raise NativeAudioError(
            f"Provider returned no text; response keys={shape}. Do not treat HTTP success as audio-consumption proof."
        )
    result = {
        "success": True,
        "dry_run": False,
        "provider": runtime.get("requested_provider") or runtime.get("provider"),
        "resolved_provider": runtime.get("provider"),
        "model": runtime.get("model"),
        "protocol": protocol,
        "mime_type": mime,
        "bytes": size,
        "text": text,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(text)
    return 0


def print_adapters(_: argparse.Namespace) -> int:
    print(
        json.dumps(
            {
                "version": VERSION,
                "protocols": [
                    {
                        "name": "gemini-native-inline",
                        "auto": "native generativelanguage.googleapis.com endpoints only",
                        "input_formats": sorted(SUPPORTED_SUFFIXES),
                    },
                    {
                        "name": "openai-chat-input-audio",
                        "auto": False,
                        "input_formats": [".mp3", ".wav"],
                    },
                    {
                        "name": "openai-chat-data-url",
                        "auto": False,
                        "compatibility_only": True,
                        "input_formats": sorted(SUPPORTED_SUFFIXES),
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    adapters = subparsers.add_parser("adapters", help="list supported protocol adapters")
    adapters.set_defaults(func=print_adapters)

    send = subparsers.add_parser("send", help="send one audio file to a model")
    send.add_argument("--audio", required=True, help="absolute or home-relative local audio path")
    send.add_argument("--prompt", required=True, help="instruction sent with the audio")
    send.add_argument("--runtime", choices=("hermes", "explicit"), default="hermes")
    send.add_argument("--provider", help="Hermes Provider/session override or explicit display label")
    send.add_argument("--model", help="model override; required in explicit mode")
    send.add_argument("--base-url", help="credential-free API base URL; required in explicit mode")
    send.add_argument("--api-key-env", help="environment variable containing the Provider credential")
    send.add_argument("--protocol", choices=PROTOCOLS, default="auto")
    send.add_argument("--auth", choices=AUTH_MODES, default="auto")
    send.add_argument("--max-bytes", type=positive_int, default=DEFAULT_MAX_BYTES)
    send.add_argument("--timeout", type=positive_int, default=DEFAULT_TIMEOUT)
    send.add_argument("--dry-run", action="store_true", help="validate and print a redacted plan")
    send.add_argument("--json", action="store_true", help="print a structured result envelope")
    send.set_defaults(func=run_send)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"error: {sanitized_error(exc)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
