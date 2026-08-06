"""Minimal, file-native custody for text materials attached to formal AIOS Matters.

This module deliberately owns no Matter lifecycle, task, Policy, index, event, or
Source Registry state.  It reads those live authorities through resolver
callbacks and writes only a per-Matter manifest plus optional immutable bytes.
"""
from __future__ import annotations

import ctypes
import datetime as dt
import errno
import fnmatch
import hashlib
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover - keeps the wider aios CLI importable on Windows
    fcntl = None  # type: ignore[assignment]

MANIFEST_SCHEMA = "aios.matter.materials.v0"
ATTACH_SCHEMA = "aios.matter.material-attach.v0"
LIST_SCHEMA = "aios.matter.material-list.v0"
VERIFY_SCHEMA = "aios.matter.material-verify.v0"
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
ROLES = {"reference", "evidence", "decision_input", "deliverable"}
CUSTODY_MODES = {"reference_only", "immutable_snapshot"}
CALLER_SENSITIVITY = {"internal", "internal_restricted"}
SOURCE_SENSITIVITY = {"public", "internal", "private", "sensitive", "mixed"}
SOURCE_KINDS = {"data_root", "worksite_root", "vault", "managed_zone", "project_connector", "service_view"}
SOURCE_ACCESS_MODES = {"read_only_reference", "maintain_in_place", "curate_reversible", "source_specific"}
SOURCE_SYNC_MODES = {"none", "device_authoritative_mirror", "managed_bidirectional", "server_canonical_replica", "metadata_only_remote"}
SOURCE_BACKUP_STATES = {"unknown", "not_required", "planned", "verified"}
SOURCE_STATES = {"match", "missing", "drifted", "unreadable", "unsafe"}
SNAPSHOT_STATES = {"not_required", "match", "missing", "drifted", "unreadable", "unsafe"}

MatterResolver = Callable[[str], dict[str, Any] | None]
SourceResolver = Callable[[str], dict[str, Any] | None]

_DIR_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
_WRITE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)

_RECORD_KEYS = {
    "material_id",
    "matter_id",
    "role",
    "attached_at",
    "source",
    "authority",
    "custody",
    "snapshot_relative_path",
    "sensitivity",
    "adoption",
    "execution",
    "lifecycle_effect",
}
_SOURCE_KEYS = {"source_id", "owner_ref", "relative_path", "file_kind", "sha256", "bytes"}


class MaterialError(Exception):
    """Expected fail-closed outcome with a stable machine-readable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Blob:
    data: bytes
    sha256: str
    size: int
    identity: tuple[int, int, int, int]


def _json_digest(value: dict[str, str]) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _material_id(matter_id: str, source_id: str, owner_ref: str, relative_path: str, role: str) -> str:
    return "mat_" + _json_digest(
        {
            "matter_id": matter_id,
            "owner_ref": owner_ref,
            "relative_path": relative_path,
            "role": role,
            "source_id": source_id,
        }
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(st: os.stat_result) -> tuple[int, int, int, int]:
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def _safe_component(value: str, *, label: str) -> str:
    if not value or len(value) > 255 or value in {".", ".."} or "/" in value or "\x00" in value:
        raise MaterialError(f"invalid_{label}", f"{label} is not a safe path component")
    if not value.isascii() or any(not (char.isalnum() or char in "._-") for char in value):
        raise MaterialError(f"invalid_{label}", f"{label} contains unsupported path characters")
    return value


def _validate_locator(locator: str) -> tuple[str, tuple[str, ...]]:
    if not isinstance(locator, str) or not locator or len(locator) > 4096 or "\x00" in locator or "\\" in locator:
        raise MaterialError("invalid_locator", "locator must be a non-empty POSIX root-relative path")
    if locator.startswith("/"):
        raise MaterialError("invalid_locator", "locator must not be absolute")
    parts = tuple(locator.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise MaterialError("invalid_locator", "locator must not contain empty, dot, or parent components")
    if any(len(part.encode("utf-8")) > 255 for part in parts):
        raise MaterialError("invalid_locator", "locator contains an overlong component")
    return "/".join(parts), parts


def _expand_local_root(home: Path, raw: Any) -> Path:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise MaterialError("source_metadata_conflict", "local Source root is missing or invalid")
    value = raw.strip()
    path = home / value[2:] if value.startswith("~/") else Path(os.path.expandvars(value)).expanduser()
    if not path.is_absolute():
        raise MaterialError("source_metadata_conflict", "local Source root must be absolute or home-relative")
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise MaterialError("source_metadata_conflict", f"local Source root cannot be resolved: {exc}") from exc


def _resolve_record(resolver: SourceResolver, query: str) -> dict[str, Any]:
    try:
        record = resolver(query)
    except Exception as exc:
        raise MaterialError("source_metadata_conflict", f"Source identity is conflicting: {query}: {exc}") from exc
    if not isinstance(record, dict):
        raise MaterialError("source_not_found", f"registered Source not found: {query}")
    if record.get("record_type") == "project_projection":
        raise MaterialError("source_metadata_conflict", f"Source must be an explicit Source Registry record: {query}")
    source_id = record.get("id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise MaterialError("source_metadata_conflict", "Source record has no canonical id")
    authority = record.get("authority")
    if not isinstance(authority, str) or not authority.strip():
        raise MaterialError("source_metadata_conflict", f"Source authority is missing or invalid: {source_id}")
    if record.get("status") not in {"active", "paused"}:
        raise MaterialError("source_metadata_conflict", f"Source status is not attachable: {source_id}")
    enum_checks = [
        ("kind", SOURCE_KINDS),
        ("access_mode", SOURCE_ACCESS_MODES),
        ("sync_mode", SOURCE_SYNC_MODES),
        ("backup_status", SOURCE_BACKUP_STATES),
        ("sensitivity", SOURCE_SENSITIVITY),
    ]
    for field, allowed in enum_checks:
        if record.get(field) not in allowed:
            raise MaterialError("source_metadata_conflict", f"Source {field} is unknown: {source_id}")
    locations = record.get("locations")
    if not isinstance(locations, list) or len(locations) != 1:
        raise MaterialError("source_metadata_conflict", f"Source must resolve to exactly one local root: {source_id}")
    location = locations[0]
    if not isinstance(location, dict) or set(location) - {"kind", "path"} or location.get("kind") != "local":
        raise MaterialError("source_metadata_conflict", f"Source must resolve to exactly one local root: {source_id}")
    if not location.get("path"):
        raise MaterialError("source_metadata_conflict", f"Source local root is missing: {source_id}")
    return record


def _source_context(
    home: Path,
    resolver: SourceResolver,
    query: str,
    *,
    locator: str,
    sensitivity: str,
) -> tuple[dict[str, Any], Path]:
    record = _resolve_record(resolver, query)
    source_id = str(record["id"])
    source_sensitivity = record.get("sensitivity")
    if source_sensitivity not in SOURCE_SENSITIVITY:
        raise MaterialError("source_metadata_conflict", f"Source sensitivity is unknown: {source_id}")
    if source_sensitivity == "sensitive":
        raise MaterialError("source_sensitivity_rejected", f"sensitive Source records are not accepted in Matter materials v0: {source_id}")
    if source_sensitivity == "mixed" and sensitivity != "internal_restricted":
        raise MaterialError(
            "source_sensitivity_requires_internal_restricted",
            f"mixed Source records require explicit internal_restricted handling: {source_id}",
        )

    include = record.get("include", [])
    exclude = record.get("exclude", [])
    if not isinstance(include, list) or not isinstance(exclude, list):
        raise MaterialError("source_metadata_conflict", f"Source path policy is invalid: {source_id}")
    if not all(isinstance(item, str) and item for item in [*include, *exclude]):
        raise MaterialError("source_metadata_conflict", f"Source path policy contains an unknown rule: {source_id}")
    included = not include or any(fnmatch.fnmatchcase(locator, pattern) for pattern in include)
    excluded = any(fnmatch.fnmatchcase(locator, pattern) for pattern in exclude)
    if not included:
        raise MaterialError("source_path_not_included", f"locator is outside the Source include policy: {locator}")
    if excluded:
        raise MaterialError("source_path_excluded", f"locator is excluded by Source policy: {locator}")

    root = _expand_local_root(home, record["locations"][0]["path"])
    return record, root


def _managed_context(
    home: Path,
    resolver: SourceResolver,
    *,
    require_backup: bool,
) -> tuple[dict[str, Any], Path]:
    record = _resolve_record(resolver, "aios-managed-zone")
    if record.get("id") != "aios-managed-zone":
        raise MaterialError("managed_zone_invalid", "aios-managed-zone did not resolve to its canonical Source id")
    if record.get("kind") != "managed_zone" or record.get("access_mode") != "curate_reversible":
        raise MaterialError("managed_zone_invalid", "aios-managed-zone metadata does not authorize reversible managed writes")
    root = _expand_local_root(home, record["locations"][0]["path"])
    managed = root / "managed"
    try:
        st = managed.lstat()
    except FileNotFoundError as exc:
        raise MaterialError("managed_zone_invalid", f"Managed Zone containment does not exist: {managed}") from exc
    except OSError as exc:
        raise MaterialError("managed_zone_invalid", f"Managed Zone containment is unreadable: {managed}: {exc}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise MaterialError("managed_zone_invalid", f"Managed Zone containment is not a non-symlink directory: {managed}")
    if require_backup and record.get("backup_status") not in {"planned", "verified"}:
        raise MaterialError(
            "managed_zone_backup_unsupported",
            f"immutable_snapshot requires live Managed Zone backup_status planned or verified, got {record.get('backup_status')!r}",
        )
    return record, managed


def _resolve_matter(resolver: MatterResolver, query: str, *, attach: bool) -> dict[str, Any]:
    try:
        record = resolver(query)
    except Exception as exc:
        raise MaterialError("matter_ambiguous", f"Matter cannot be resolved uniquely: {query}: {exc}") from exc
    if not isinstance(record, dict):
        raise MaterialError("matter_not_found", f"Matter not found: {query}")
    if record.get("record_type") != "matter":
        raise MaterialError("matter_not_attachable", f"inferred Worksites are not formal Matters: {query}")
    matter_id = record.get("id")
    if not isinstance(matter_id, str):
        raise MaterialError("matter_not_attachable", "formal Matter has no stable id")
    _safe_component(matter_id, label="matter_id")
    if attach:
        raw_state = record.get("_material_raw_lifecycle_state")
        if not isinstance(raw_state, str) or raw_state not in {"active", "paused"}:
            raise MaterialError(
                "matter_not_attachable",
                f"Matter raw lifecycle.state must be exactly active or paused, got {raw_state!r}",
            )
    return record


def _open_root_dir(path: Path, *, code: str, detail: str) -> int:
    try:
        return os.open(path, _DIR_FLAGS)
    except FileNotFoundError as exc:
        raise MaterialError(code, f"{detail} is missing: {path}") from exc
    except OSError as exc:
        raise MaterialError(code, f"{detail} is unsafe or unreadable: {path}: {exc.strerror}") from exc


def _open_content_root(path: Path, *, label: str) -> int:
    try:
        return os.open(path, _DIR_FLAGS)
    except FileNotFoundError as exc:
        raise MaterialError(f"{label}_missing", f"{label} root is missing: {path}") from exc
    except OSError as exc:
        code = f"{label}_unsafe" if exc.errno in {errno.ELOOP, errno.ENOTDIR} else f"{label}_unreadable"
        raise MaterialError(code, f"{label} root is unsafe or unreadable: {path}: {exc.strerror}") from exc


def _open_dir_at(parent_fd: int, name: str, *, label: str) -> int:
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=parent_fd)
    except FileNotFoundError as exc:
        raise MaterialError(f"{label}_missing", f"{label} directory is missing") from exc
    except OSError as exc:
        code = f"{label}_unsafe" if exc.errno in {errno.ELOOP, errno.ENOTDIR} else f"{label}_unreadable"
        raise MaterialError(code, f"{label} directory is unsafe or unreadable: {exc.strerror}") from exc


def _open_or_create_dir(parent_fd: int, name: str, *, label: str) -> int:
    created = False
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        created = True
    except FileExistsError:
        pass
    except OSError as exc:
        raise MaterialError(f"{label}_unreadable", f"cannot create {label} directory: {exc.strerror}") from exc
    fd = _open_dir_at(parent_fd, name, label=label)
    if created:
        try:
            os.fsync(parent_fd)
        except OSError as exc:
            os.close(fd)
            raise MaterialError(f"{label}_unreadable", f"cannot fsync parent after creating {label}: {exc.strerror}") from exc
    return fd


def _stat_relative(root_fd: int, parts: tuple[str, ...], *, label: str) -> os.stat_result:
    current = os.dup(root_fd)
    try:
        for component in parts[:-1]:
            next_fd = _open_dir_at(current, component, label=label)
            os.close(current)
            current = next_fd
        try:
            leaf_fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=current)
        except FileNotFoundError as exc:
            raise MaterialError(f"{label}_missing", f"{label} is missing") from exc
        except PermissionError as exc:
            raise MaterialError(f"{label}_unreadable", f"{label} cannot be read") from exc
        except OSError as exc:
            code = f"{label}_unsafe" if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EISDIR} else f"{label}_unreadable"
            raise MaterialError(code, f"{label} is unsafe or unreadable: {exc.strerror}") from exc
        try:
            st = os.fstat(leaf_fd)
        finally:
            os.close(leaf_fd)
        if not stat.S_ISREG(st.st_mode):
            raise MaterialError(f"{label}_unsafe", f"{label} is not a regular file")
        return st
    finally:
        os.close(current)


def _stable_read_from_dir(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    label: str,
    max_bytes: int = MAX_FILE_BYTES,
) -> Blob:
    current = os.dup(root_fd)
    leaf_fd: int | None = None
    try:
        for component in parts[:-1]:
            next_fd = _open_dir_at(current, component, label=label)
            os.close(current)
            current = next_fd
        try:
            leaf_fd = os.open(parts[-1], _FILE_FLAGS, dir_fd=current)
        except FileNotFoundError as exc:
            raise MaterialError(f"{label}_missing", f"{label} is missing") from exc
        except PermissionError as exc:
            raise MaterialError(f"{label}_unreadable", f"{label} cannot be read") from exc
        except OSError as exc:
            code = f"{label}_unsafe" if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.EISDIR} else f"{label}_unreadable"
            raise MaterialError(code, f"{label} is unsafe or unreadable: {exc.strerror}") from exc

        before = os.fstat(leaf_fd)
        if not stat.S_ISREG(before.st_mode):
            raise MaterialError(f"{label}_unsafe", f"{label} is not a regular file")
        if before.st_size > max_bytes:
            raise MaterialError(f"{label}_unsafe", f"{label} exceeds {max_bytes} bytes")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(leaf_fd, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise MaterialError(f"{label}_unsafe", f"{label} exceeds {max_bytes} bytes")
        after = os.fstat(leaf_fd)
        if _identity(before) != _identity(after) or total != after.st_size:
            raise MaterialError(f"{label}_changed", f"{label} changed during stable read")
        data = b"".join(chunks)
        try:
            data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MaterialError(f"{label}_unsafe", f"{label} is not strict UTF-8 text") from exc
        if b"\x00" in data:
            raise MaterialError(f"{label}_unsafe", f"{label} contains NUL bytes")
    except MaterialError:
        raise
    except OSError as exc:
        raise MaterialError(f"{label}_unreadable", f"{label} read failed: {exc.strerror}") from exc
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)
        os.close(current)

    rebound = _stat_relative(root_fd, parts, label=label)
    if _identity(rebound) != _identity(after):
        raise MaterialError(f"{label}_changed", f"{label} locator changed during stable read")
    return Blob(data=data, sha256=_sha256(data), size=len(data), identity=_identity(after))


def _stable_read_path(root: Path, parts: tuple[str, ...], *, label: str, max_bytes: int = MAX_FILE_BYTES) -> Blob:
    root_fd = _open_content_root(root, label=label)
    try:
        return _stable_read_from_dir(root_fd, parts, label=label, max_bytes=max_bytes)
    finally:
        os.close(root_fd)


def _confirm_identity(root: Path, parts: tuple[str, ...], expected: tuple[int, int, int, int]) -> None:
    root_fd = _open_root_dir(root, code="source_changed", detail="source root")
    try:
        current = _stat_relative(root_fd, parts, label="source")
    except MaterialError as exc:
        raise MaterialError("source_changed_during_attach", f"source locator changed before commit: {exc.detail}") from exc
    finally:
        os.close(root_fd)
    if _identity(current) != expected:
        raise MaterialError("source_changed_during_attach", "source locator changed before commit")


def _validate_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _validate_record(record: Any, matter_id: str) -> dict[str, Any]:
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        raise MaterialError("manifest_invalid", "material record has an unsupported shape")
    source = record.get("source")
    if not isinstance(source, dict) or set(source) != _SOURCE_KEYS:
        raise MaterialError("manifest_invalid", "material source record has an unsupported shape")
    if record.get("matter_id") != matter_id:
        raise MaterialError("manifest_invalid", "material matter_id does not match manifest owner")
    if record.get("role") not in ROLES or record.get("custody") not in CUSTODY_MODES:
        raise MaterialError("manifest_invalid", "material role or custody is invalid")
    if record.get("sensitivity") not in CALLER_SENSITIVITY:
        raise MaterialError("manifest_invalid", "material sensitivity is invalid")
    if not _validate_timestamp(record.get("attached_at")):
        raise MaterialError("manifest_invalid", "material attached_at must include an explicit UTC offset")
    fixed = {
        "authority": "source_canonical",
        "adoption": "not_adopted",
        "execution": "none",
        "lifecycle_effect": "none",
    }
    if any(record.get(key) != value for key, value in fixed.items()):
        raise MaterialError("manifest_invalid", "material authority/adoption/execution invariants are invalid")
    if source.get("file_kind") != "regular_utf8_text":
        raise MaterialError("manifest_invalid", "material source file_kind is invalid")
    for field in ["source_id", "owner_ref", "relative_path"]:
        if not isinstance(source.get(field), str) or not source[field]:
            raise MaterialError("manifest_invalid", f"material source {field} is invalid")
    relative_path, _ = _validate_locator(source["relative_path"])
    if relative_path != source["relative_path"]:
        raise MaterialError("manifest_invalid", "material relative_path is not canonical")
    digest = source.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise MaterialError("manifest_invalid", "material source sha256 is invalid")
    size = source.get("bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
        raise MaterialError("manifest_invalid", "material source bytes is invalid")
    expected_id = _material_id(
        matter_id,
        source["source_id"],
        source["owner_ref"],
        source["relative_path"],
        record["role"],
    )
    if record.get("material_id") != expected_id:
        raise MaterialError("manifest_invalid", "material_id does not match its canonical association tuple")
    expected_snapshot = f"snapshots/{digest}" if record["custody"] == "immutable_snapshot" else None
    if record.get("snapshot_relative_path") != expected_snapshot:
        raise MaterialError("manifest_invalid", "snapshot_relative_path does not match custody and source hash")
    return record


def _empty_manifest(matter_id: str) -> dict[str, Any]:
    return {"schema": MANIFEST_SCHEMA, "matter_id": matter_id, "materials": []}


def _validate_manifest(value: Any, matter_id: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schema", "matter_id", "materials"}:
        raise MaterialError("manifest_invalid", "materials.json has an unsupported shape")
    if value.get("schema") != MANIFEST_SCHEMA or value.get("matter_id") != matter_id:
        raise MaterialError("manifest_invalid", "materials.json schema or Matter owner is invalid")
    materials = value.get("materials")
    if not isinstance(materials, list):
        raise MaterialError("manifest_invalid", "materials must be an array")
    validated = [_validate_record(record, matter_id) for record in materials]
    ids = [record["material_id"] for record in validated]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise MaterialError("manifest_invalid", "materials must have unique material_id values in sorted order")
    return value


def _load_manifest_fd(matter_fd: int, matter_id: str) -> dict[str, Any]:
    try:
        blob = _stable_read_from_dir(
            matter_fd,
            ("materials.json",),
            label="manifest",
            max_bytes=MAX_MANIFEST_BYTES,
        )
    except MaterialError as exc:
        if exc.code == "manifest_missing":
            return _empty_manifest(matter_id)
        raise MaterialError("manifest_invalid", exc.detail) from exc
    try:
        value = json.loads(blob.data.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise MaterialError("manifest_invalid", f"materials.json is invalid JSON: {exc}") from exc
    return _validate_manifest(value, matter_id)


def _open_optional_matter_fd(managed: Path, matter_id: str) -> int | None:
    managed_fd = _open_root_dir(managed, code="managed_zone_invalid", detail="Managed Zone containment")
    base_fd: int | None = None
    try:
        try:
            base_fd = _open_dir_at(managed_fd, "matter-materials", label="materials_root")
        except MaterialError as exc:
            if exc.code == "materials_root_missing":
                return None
            raise MaterialError("managed_zone_invalid", exc.detail) from exc
        try:
            return _open_dir_at(base_fd, matter_id, label="matter_materials")
        except MaterialError as exc:
            if exc.code == "matter_materials_missing":
                return None
            raise MaterialError("manifest_invalid", exc.detail) from exc
    finally:
        if base_fd is not None:
            os.close(base_fd)
        os.close(managed_fd)


def _manifest_path(managed: Path, matter_id: str) -> Path:
    return managed / "matter-materials" / matter_id / "materials.json"


def _reject_source_destination_overlap(
    source_root: Path,
    parts: tuple[str, ...],
    source_identity: tuple[int, int, int, int],
    manifest_path: Path,
) -> None:
    source_path = source_root.joinpath(*parts)
    matter_root = manifest_path.parent
    try:
        source_path.relative_to(matter_root)
    except ValueError:
        pass
    else:
        raise MaterialError(
            "source_destination_overlap",
            "source leaf is inside this Matter's canonical materials directory",
        )

    source_inode = source_identity[:2]
    try:
        root_stat = matter_root.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise MaterialError(
            "source_destination_overlap",
            f"cannot safely inspect this Matter's material write surface: {exc.strerror}",
        ) from exc
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        return

    try:
        with os.scandir(matter_root) as entries:
            root_entries = list(entries)
        for entry in root_entries:
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISREG(entry_stat.st_mode) and (entry_stat.st_dev, entry_stat.st_ino) == source_inode:
                raise MaterialError(
                    "source_destination_overlap",
                    "source inode aliases this Matter's canonical material write surface",
                )
            if entry.name != "snapshots" or not stat.S_ISDIR(entry_stat.st_mode):
                continue
            with os.scandir(entry.path) as snapshots:
                for snapshot in snapshots:
                    try:
                        snapshot_stat = snapshot.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    if stat.S_ISREG(snapshot_stat.st_mode) and (snapshot_stat.st_dev, snapshot_stat.st_ino) == source_inode:
                        raise MaterialError(
                            "source_destination_overlap",
                            "source inode aliases this Matter's canonical material write surface",
                        )
    except MaterialError:
        raise
    except OSError as exc:
        raise MaterialError(
            "source_destination_overlap",
            f"cannot safely inspect this Matter's material write surface: {exc.strerror}",
        ) from exc


def _build_record(
    *,
    matter_id: str,
    source_id: str,
    owner_ref: str,
    locator: str,
    role: str,
    custody: str,
    sensitivity: str,
    blob: Blob,
) -> dict[str, Any]:
    return {
        "material_id": _material_id(matter_id, source_id, owner_ref, locator, role),
        "matter_id": matter_id,
        "role": role,
        "attached_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": {
            "source_id": source_id,
            "owner_ref": owner_ref,
            "relative_path": locator,
            "file_kind": "regular_utf8_text",
            "sha256": blob.sha256,
            "bytes": blob.size,
        },
        "authority": "source_canonical",
        "custody": custody,
        "snapshot_relative_path": f"snapshots/{blob.sha256}" if custody == "immutable_snapshot" else None,
        "sensitivity": sensitivity,
        "adoption": "not_adopted",
        "execution": "none",
        "lifecycle_effect": "none",
    }


def _decide(
    manifest: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[str, dict[str, Any], bool, bool]:
    by_id = {record["material_id"]: record for record in manifest["materials"]}
    existing = by_id.get(candidate["material_id"])
    if existing is None:
        return "attached", candidate, True, candidate["custody"] == "immutable_snapshot"
    existing_source = existing["source"]
    candidate_source = candidate["source"]
    if (
        existing_source["sha256"] != candidate_source["sha256"]
        or existing_source["bytes"] != candidate_source["bytes"]
    ):
        raise MaterialError("source_drift_conflict", "the same association now resolves to different source bytes")
    if existing["sensitivity"] != candidate["sensitivity"]:
        raise MaterialError("association_metadata_conflict", "the same association already has a different sensitivity")
    if existing["custody"] == "immutable_snapshot":
        return "already_attached", existing, False, True
    if candidate["custody"] == "reference_only":
        return "already_attached", existing, False, False
    upgraded = dict(existing)
    upgraded["custody"] = "immutable_snapshot"
    upgraded["snapshot_relative_path"] = f"snapshots/{existing_source['sha256']}"
    return "custody_upgraded", upgraded, True, True


def _snapshot_blob(matter_fd: int, digest: str) -> Blob | None:
    try:
        snapshots_fd = _open_dir_at(matter_fd, "snapshots", label="snapshot")
    except MaterialError as exc:
        if exc.code == "snapshot_missing":
            return None
        raise MaterialError("snapshot_conflict", exc.detail) from exc
    try:
        try:
            return _stable_read_from_dir(snapshots_fd, (digest,), label="snapshot")
        except MaterialError as exc:
            if exc.code == "snapshot_missing":
                return None
            raise MaterialError("snapshot_conflict", exc.detail) from exc
    finally:
        os.close(snapshots_fd)


def _check_snapshot(matter_fd: int | None, blob: Blob, *, must_exist: bool) -> None:
    existing = _snapshot_blob(matter_fd, blob.sha256) if matter_fd is not None else None
    if existing is None:
        if must_exist:
            raise MaterialError("snapshot_conflict", "an attached immutable snapshot is missing")
        return
    if existing.sha256 != blob.sha256 or existing.size != blob.size:
        raise MaterialError("snapshot_conflict", "existing snapshot bytes do not match the declared source hash")


def _rename_noreplace(dir_fd: int, source_name: str, target_name: str) -> None:
    if not sys.platform.startswith("linux"):
        raise MaterialError("unsupported_platform", "immutable_snapshot atomic no-replace install is Linux-only")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise MaterialError("unsupported_platform", "renameat2 is unavailable; refusing non-atomic snapshot install")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(dir_fd, os.fsencode(source_name), dir_fd, os.fsencode(target_name), 1)
    if result == 0:
        return
    code = ctypes.get_errno()
    if code in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(code, os.strerror(code), target_name)
    raise OSError(code, os.strerror(code), target_name)


def _write_all(fd: int, value: bytes) -> None:
    view = memoryview(value)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        view = view[written:]


def _install_snapshot(matter_fd: int, blob: Blob, *, allow_create: bool) -> None:
    try:
        snapshots_fd = _open_dir_at(matter_fd, "snapshots", label="snapshot")
    except MaterialError as exc:
        if exc.code != "snapshot_missing":
            raise MaterialError("snapshot_conflict", exc.detail) from exc
        if not allow_create:
            raise MaterialError("snapshot_conflict", "an attached immutable snapshot is missing") from exc
        snapshots_fd = _open_or_create_dir(matter_fd, "snapshots", label="snapshot")
    try:
        try:
            current = _stable_read_from_dir(snapshots_fd, (blob.sha256,), label="snapshot")
        except MaterialError as exc:
            if exc.code != "snapshot_missing":
                raise MaterialError("snapshot_conflict", exc.detail) from exc
            current = None
        if current is not None:
            if current.sha256 != blob.sha256 or current.size != blob.size:
                raise MaterialError("snapshot_conflict", "existing snapshot bytes do not match the declared source hash")
            return
        if not allow_create:
            raise MaterialError("snapshot_conflict", "an attached immutable snapshot is missing")

        stage_name = f".{blob.sha256}.tmp-{os.getpid()}-{secrets.token_hex(8)}"
        stage_exists = False
        try:
            stage_fd = os.open(stage_name, _WRITE_FLAGS, 0o600, dir_fd=snapshots_fd)
            stage_exists = True
            try:
                _write_all(stage_fd, blob.data)
                os.fsync(stage_fd)
            finally:
                os.close(stage_fd)
            staged = _stable_read_from_dir(snapshots_fd, (stage_name,), label="snapshot_staging")
            if staged.sha256 != blob.sha256 or staged.size != blob.size:
                raise MaterialError("snapshot_conflict", "snapshot staging readback did not match source bytes")
            try:
                _rename_noreplace(snapshots_fd, stage_name, blob.sha256)
                stage_exists = False
                os.fsync(snapshots_fd)
            except FileExistsError:
                os.unlink(stage_name, dir_fd=snapshots_fd)
                stage_exists = False
            installed = _stable_read_from_dir(snapshots_fd, (blob.sha256,), label="snapshot")
            if installed.sha256 != blob.sha256 or installed.size != blob.size:
                raise MaterialError("snapshot_conflict", "installed snapshot readback did not match source bytes")
        finally:
            if stage_exists:
                try:
                    os.unlink(stage_name, dir_fd=snapshots_fd)
                except FileNotFoundError:
                    pass
    except MaterialError:
        raise
    except OSError as exc:
        raise MaterialError("snapshot_conflict", f"snapshot install failed: {exc.strerror}") from exc
    finally:
        os.close(snapshots_fd)


def _write_manifest(matter_fd: int, value: dict[str, Any]) -> None:
    normalized = dict(value)
    normalized["materials"] = sorted(value["materials"], key=lambda record: record["material_id"])
    _validate_manifest(normalized, normalized["matter_id"])
    payload = (json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temp_name = f".materials.json.tmp-{os.getpid()}-{secrets.token_hex(8)}"
    exists = False
    try:
        temp_fd = os.open(temp_name, _WRITE_FLAGS, 0o600, dir_fd=matter_fd)
        exists = True
        try:
            _write_all(temp_fd, payload)
            os.fsync(temp_fd)
        finally:
            os.close(temp_fd)
        readback = _stable_read_from_dir(matter_fd, (temp_name,), label="manifest_staging", max_bytes=MAX_MANIFEST_BYTES)
        if readback.data != payload:
            raise MaterialError("manifest_write_failed", "manifest staging readback changed")
        os.replace(temp_name, "materials.json", src_dir_fd=matter_fd, dst_dir_fd=matter_fd)
        exists = False
        os.fsync(matter_fd)
    except MaterialError:
        raise
    except OSError as exc:
        raise MaterialError("manifest_write_failed", f"atomic manifest replacement failed: {exc.strerror}") from exc
    finally:
        if exists:
            try:
                os.unlink(temp_name, dir_fd=matter_fd)
            except FileNotFoundError:
                pass


def _attach_failure(exc: MaterialError, *, dry_run: bool) -> dict[str, Any]:
    return {
        "schema": ATTACH_SCHEMA,
        "ok": False,
        "status": exc.code,
        "dry_run": dry_run,
        "error": exc.detail,
    }


def attach_material(
    home: Path,
    matter_query: str,
    *,
    source_query: str,
    owner_ref: str,
    locator: str,
    role: str,
    custody: str,
    sensitivity: str,
    dry_run: bool,
    resolve_matter: MatterResolver,
    resolve_source: SourceResolver,
) -> dict[str, Any]:
    """Attach one source-owned text file, or perform the same preflight read-only."""
    try:
        if role not in ROLES or custody not in CUSTODY_MODES or sensitivity not in CALLER_SENSITIVITY:
            raise MaterialError("invalid_request", "role, custody, and sensitivity must be explicit v0 enum values")
        if not isinstance(owner_ref, str) or not owner_ref.strip() or len(owner_ref) > 1024 or "\x00" in owner_ref:
            raise MaterialError("invalid_owner_ref", "owner_ref must be an explicit non-empty stable reference")
        owner_ref = owner_ref.strip()
        locator, parts = _validate_locator(locator)
        matter = _resolve_matter(resolve_matter, matter_query, attach=True)
        matter_id = str(matter["id"])
        source_record, source_root = _source_context(
            home,
            resolve_source,
            source_query,
            locator=locator,
            sensitivity=sensitivity,
        )
        source_id = str(source_record["id"])
        blob = _stable_read_path(source_root, parts, label="source")
        managed_record, managed = _managed_context(
            home,
            resolve_source,
            require_backup=custody == "immutable_snapshot",
        )
        if custody == "immutable_snapshot" and not sys.platform.startswith("linux"):
            raise MaterialError("unsupported_platform", "immutable_snapshot atomic no-replace install is Linux-only")
        candidate = _build_record(
            matter_id=matter_id,
            source_id=source_id,
            owner_ref=owner_ref,
            locator=locator,
            role=role,
            custody=custody,
            sensitivity=sensitivity,
            blob=blob,
        )
        manifest_path = _manifest_path(managed, matter_id)
        _reject_source_destination_overlap(source_root, parts, blob.identity, manifest_path)

        if dry_run:
            matter_fd = _open_optional_matter_fd(managed, matter_id)
            try:
                manifest = _load_manifest_fd(matter_fd, matter_id) if matter_fd is not None else _empty_manifest(matter_id)
                status, record, write_manifest, uses_snapshot = _decide(manifest, candidate)
                if uses_snapshot:
                    _check_snapshot(
                        matter_fd,
                        blob,
                        must_exist=record["custody"] == "immutable_snapshot" and not write_manifest,
                    )
                _confirm_identity(source_root, parts, blob.identity)
            finally:
                if matter_fd is not None:
                    os.close(matter_fd)
            dry_status = {
                "attached": "would_attach",
                "custody_upgraded": "would_upgrade_custody",
            }.get(status, status)
            return {
                "schema": ATTACH_SCHEMA,
                "ok": True,
                "status": dry_status,
                "dry_run": True,
                "matter_id": matter_id,
                "material_id": record["material_id"],
                "manifest_path": str(manifest_path),
                "snapshot_path": str(manifest_path.parent / record["snapshot_relative_path"])
                if record["snapshot_relative_path"]
                else None,
                "managed_zone_backup_status": managed_record.get("backup_status"),
                "record": record,
            }

        if fcntl is None:
            raise MaterialError("unsupported_platform", "Matter material attach requires local directory flock support")
        managed_fd = _open_root_dir(managed, code="managed_zone_invalid", detail="Managed Zone containment")
        materials_fd: int | None = None
        matter_fd: int | None = None
        try:
            materials_fd = _open_or_create_dir(managed_fd, "matter-materials", label="materials_root")
            matter_fd = _open_or_create_dir(materials_fd, matter_id, label="matter_materials")
            fcntl.flock(matter_fd, fcntl.LOCK_EX)
            manifest = _load_manifest_fd(matter_fd, matter_id)
            _confirm_identity(source_root, parts, blob.identity)
            status, record, write_manifest, uses_snapshot = _decide(manifest, candidate)
            if uses_snapshot:
                _install_snapshot(matter_fd, blob, allow_create=write_manifest)
            if write_manifest:
                records = [item for item in manifest["materials"] if item["material_id"] != record["material_id"]]
                records.append(record)
                _write_manifest(
                    matter_fd,
                    {"schema": MANIFEST_SCHEMA, "matter_id": matter_id, "materials": records},
                )
        finally:
            if matter_fd is not None:
                try:
                    fcntl.flock(matter_fd, fcntl.LOCK_UN)
                finally:
                    os.close(matter_fd)
            if materials_fd is not None:
                os.close(materials_fd)
            os.close(managed_fd)

        return {
            "schema": ATTACH_SCHEMA,
            "ok": True,
            "status": status,
            "dry_run": False,
            "matter_id": matter_id,
            "material_id": record["material_id"],
            "manifest_path": str(manifest_path),
            "snapshot_path": str(manifest_path.parent / record["snapshot_relative_path"])
            if record["snapshot_relative_path"]
            else None,
            "managed_zone_backup_status": managed_record.get("backup_status"),
            "record": record,
        }
    except MaterialError as exc:
        return _attach_failure(exc, dry_run=dry_run)
    except OSError as exc:
        return _attach_failure(MaterialError("io_error", f"Matter material attach I/O failed: {exc.strerror}"), dry_run=dry_run)


def list_materials(
    home: Path,
    matter_query: str,
    *,
    resolve_matter: MatterResolver,
    resolve_source: SourceResolver,
) -> dict[str, Any]:
    """Read only materials.json; do not inspect source or snapshot bytes."""
    try:
        matter = _resolve_matter(resolve_matter, matter_query, attach=False)
        matter_id = str(matter["id"])
        _, managed = _managed_context(home, resolve_source, require_backup=False)
        matter_fd = _open_optional_matter_fd(managed, matter_id)
        try:
            manifest = _load_manifest_fd(matter_fd, matter_id) if matter_fd is not None else _empty_manifest(matter_id)
        finally:
            if matter_fd is not None:
                os.close(matter_fd)
        projection = []
        for record in manifest["materials"]:
            row = dict(record)
            row["source_state"] = "unchecked"
            row["snapshot_state"] = "unchecked" if record["custody"] == "immutable_snapshot" else "not_required"
            projection.append(row)
        return {
            "schema": LIST_SCHEMA,
            "ok": True,
            "matter_id": matter_id,
            "manifest_path": str(_manifest_path(managed, matter_id)),
            "count": len(projection),
            "materials": projection,
        }
    except MaterialError as exc:
        return {"schema": LIST_SCHEMA, "ok": False, "status": exc.code, "error": exc.detail, "materials": []}
    except OSError as exc:
        return {"schema": LIST_SCHEMA, "ok": False, "status": "io_error", "error": f"Matter material list I/O failed: {exc.strerror}", "materials": []}


def _state_for_blob(
    root_fd: int,
    parts: tuple[str, ...],
    *,
    label: str,
    expected_sha256: str,
    expected_bytes: int,
) -> str:
    try:
        blob = _stable_read_from_dir(root_fd, parts, label=label)
    except MaterialError as exc:
        suffix = exc.code.removeprefix(f"{label}_")
        if suffix == "missing":
            return "missing"
        if suffix == "unsafe":
            return "unsafe"
        return "unreadable"
    return "match" if blob.sha256 == expected_sha256 and blob.size == expected_bytes else "drifted"


def _source_state(
    home: Path,
    resolver: SourceResolver,
    record: dict[str, Any],
) -> str:
    source = record["source"]
    locator = source["relative_path"]
    _, parts = _validate_locator(locator)
    try:
        _, root = _source_context(
            home,
            resolver,
            source["source_id"],
            locator=locator,
            sensitivity=record["sensitivity"],
        )
        root_fd = _open_content_root(root, label="source")
    except MaterialError as exc:
        if exc.code == "source_missing":
            return "missing"
        return "unsafe"
    try:
        return _state_for_blob(
            root_fd,
            parts,
            label="source",
            expected_sha256=source["sha256"],
            expected_bytes=source["bytes"],
        )
    finally:
        os.close(root_fd)


def _snapshot_state(matter_fd: int, record: dict[str, Any]) -> str:
    if record["custody"] == "reference_only":
        return "not_required"
    source = record["source"]
    return _state_for_blob(
        matter_fd,
        ("snapshots", source["sha256"]),
        label="snapshot",
        expected_sha256=source["sha256"],
        expected_bytes=source["bytes"],
    )


def _verdict(custody: str, source_state: str, snapshot_state: str) -> str:
    if custody == "reference_only":
        return "pass" if source_state == "match" and snapshot_state == "not_required" else "fail"
    if snapshot_state != "match":
        return "fail"
    return "pass" if source_state == "match" else "recoverable_warning"


def _verdict_message(verdict: str) -> str:
    if verdict == "pass":
        return "原文件和所需校验副本完整；事务状态未改变。"
    if verdict == "recoverable_warning":
        return "原位置缺失或内容已变化，但原校验副本仍完整可用；没有自动改绑。"
    return "当前无法证明所声明的材料/副本完整；记录仍保留，未覆盖任何文件。"


def verify_materials(
    home: Path,
    matter_query: str,
    *,
    material_id: str | None,
    verify_all: bool,
    resolve_matter: MatterResolver,
    resolve_source: SourceResolver,
) -> dict[str, Any]:
    """Fresh-read source and snapshot bytes without updating any persisted state."""
    try:
        if material_id and verify_all:
            raise MaterialError("invalid_request", "choose one material_id or --all, not both")
        matter = _resolve_matter(resolve_matter, matter_query, attach=False)
        matter_id_value = str(matter["id"])
        _, managed = _managed_context(home, resolve_source, require_backup=False)
        matter_fd = _open_optional_matter_fd(managed, matter_id_value)
        if matter_fd is None:
            manifest = _empty_manifest(matter_id_value)
        else:
            manifest = _load_manifest_fd(matter_fd, matter_id_value)
        try:
            selected = manifest["materials"]
            if material_id:
                selected = [record for record in selected if record["material_id"] == material_id]
                if not selected:
                    raise MaterialError("material_not_found", f"material not found in Matter: {material_id}")
            results: list[dict[str, Any]] = []
            for record in selected:
                source_state = _source_state(home, resolve_source, record)
                snapshot_state = (
                    _snapshot_state(matter_fd, record)
                    if matter_fd is not None
                    else ("not_required" if record["custody"] == "reference_only" else "missing")
                )
                if source_state not in SOURCE_STATES or snapshot_state not in SNAPSHOT_STATES:
                    raise MaterialError("verification_internal_error", "verification produced an unsupported state")
                verdict = _verdict(record["custody"], source_state, snapshot_state)
                results.append(
                    {
                        "material_id": record["material_id"],
                        "source_state": source_state,
                        "snapshot_state": snapshot_state,
                        "verdict": verdict,
                        "message": _verdict_message(verdict),
                    }
                )
        finally:
            if matter_fd is not None:
                os.close(matter_fd)
        failed = any(result["verdict"] == "fail" for result in results)
        warned = any(result["verdict"] == "recoverable_warning" for result in results)
        return {
            "schema": VERIFY_SCHEMA,
            "ok": not failed,
            "status": "fail" if failed else "recoverable_warning" if warned else "pass",
            "matter_id": matter_id_value,
            "manifest_path": str(_manifest_path(managed, matter_id_value)),
            "results": results,
        }
    except MaterialError as exc:
        return {
            "schema": VERIFY_SCHEMA,
            "ok": False,
            "status": exc.code,
            "error": exc.detail,
            "results": [],
        }
    except OSError as exc:
        return {
            "schema": VERIFY_SCHEMA,
            "ok": False,
            "status": "io_error",
            "error": f"Matter material verify I/O failed: {exc.strerror}",
            "results": [],
        }
