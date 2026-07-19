"""Narrow, read-only validation for explicitly authorized AIOS asset promotions."""
from __future__ import annotations

import ctypes
import datetime as dt
import errno
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

CHANGE_SET_SCHEMAS = {"aios.asset-promotion-change-set.v0"}
RECEIPT_SCHEMAS = {"aios.asset-promotion-receipt.v0"}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ref_path(raw: Any, *, anchor: Path) -> Path | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(os.path.expandvars(raw)).expanduser()
    if not path.is_absolute():
        path = anchor.parent / path
    return path.resolve()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError(f"promotion record not found: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid promotion JSON {path}: {exc}")
    if not isinstance(value, dict):
        raise ValueError(f"promotion record must be a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _rename_directory_noreplace(source: Path, target: Path) -> None:
    """Atomically install one directory without replacing an existing target."""
    if not sys.platform.startswith("linux"):
        raise OSError(errno.ENOTSUP, "atomic no-replace directory install is currently supported only on Linux")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOTSUP, "renameat2 is unavailable; refusing non-atomic promotion install")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(target), 1)
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise FileExistsError(code, os.strerror(code), str(target))
        raise OSError(code, os.strerror(code), str(target))


def apply_promotion(
    home: Path,
    supplied_path: Path,
    *,
    apply: bool,
    resolve_owner: Callable[[str], dict[str, Any] | None],
    work_root: Path,
) -> dict[str, Any]:
    """Plan or apply one explicitly authorized copy-if-absent promotion."""
    change_path = supplied_path.expanduser().resolve()
    try:
        change = _load_json(change_path)
    except ValueError as exc:
        return {
            "schema": "aios.asset-promotion-apply.v1",
            "ok": False,
            "status": "rejected",
            "errors": [str(exc)],
            "warnings": [],
        }

    if change.get("status") == "applied_validated":
        validation = validate_promotion(
            home,
            change_path,
            resolve_owner=resolve_owner,
            work_root=work_root,
        )
        return {
            "schema": "aios.asset-promotion-apply.v1",
            "ok": validation["ok"],
            "status": "already_applied_validated" if validation["ok"] else "existing_application_invalid",
            "change_set_path": str(change_path),
            "target_directory": validation.get("target_directory"),
            "validation": validation,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", []),
        }

    errors: list[str] = []
    warnings: list[str] = []

    def require(name: str, condition: bool, detail: str) -> None:
        if not condition:
            errors.append(f"{name}: {detail}")

    require("change_set_schema", change.get("schema") in CHANGE_SET_SCHEMAS, str(change.get("schema")))
    require("change_set_status", change.get("status") == "authorized_pending", str(change.get("status")))
    require("change_set_id", isinstance(change.get("id"), str) and bool(str(change.get("id")).strip()), str(change.get("id")))
    gates = _dict(change.get("gates"))
    require("explicit_authorization", gates.get("explicit_authorization") == "pass", "gate must equal pass")

    source_record = _dict(change.get("source"))
    require("source_worksite_id", isinstance(source_record.get("worksite_id"), str) and bool(str(source_record.get("worksite_id")).strip()), str(source_record.get("worksite_id")))
    source_worksite = _ref_path(source_record.get("worksite_path"), anchor=change_path)
    resolved_work_root = work_root.resolve()
    require(
        "source_worksite",
        bool(source_worksite and source_worksite.is_dir() and source_worksite.is_relative_to(resolved_work_root)),
        f"source={source_worksite} work_root={resolved_work_root}",
    )

    target = _dict(change.get("target"))
    require("asset_id", isinstance(target.get("asset_id"), str) and bool(str(target.get("asset_id")).strip()), str(target.get("asset_id")))
    require("asset_type", isinstance(target.get("asset_type"), str) and bool(str(target.get("asset_type")).strip()), str(target.get("asset_type")))
    target_dir = _ref_path(target.get("directory"), anchor=change_path)
    owner_ref = target.get("owner_ref")
    owner_id = owner_ref.removeprefix("source:") if isinstance(owner_ref, str) and owner_ref.startswith("source:") else ""
    owner = resolve_owner(owner_id) if owner_id else None
    require("owner_ref", bool(owner_id), str(owner_ref))
    require("owner_resolves", bool(owner), str(owner_ref))
    require("owner_kind", bool(owner and owner.get("kind") == "managed_zone"), str((owner or {}).get("kind")))
    require("owner_access", bool(owner and owner.get("access_mode") == "curate_reversible"), str((owner or {}).get("access_mode")))

    locations = _list((owner or {}).get("locations"))
    local_locations = [item for item in locations if isinstance(item, dict) and item.get("kind") == "local" and item.get("path")]
    managed_root: Path | None = None
    if local_locations:
        raw_root = str(local_locations[0]["path"])
        managed_root = (home / raw_root[2:] if raw_root.startswith("~/") else Path(os.path.expandvars(raw_root)).expanduser()).resolve()
    managed_dir = (managed_root / "managed").resolve() if managed_root else None
    require(
        "target_containment",
        bool(target_dir and managed_dir and target_dir.is_relative_to(managed_dir) and target_dir != managed_dir),
        f"target={target_dir} managed={managed_dir}",
    )
    require(
        "source_target_disjoint",
        bool(
            source_worksite
            and target_dir
            and not target_dir.is_relative_to(source_worksite)
            and not source_worksite.is_relative_to(target_dir)
        ),
        f"source={source_worksite} target={target_dir}",
    )

    scope = _dict(change.get("scope"))
    selected = _list(scope.get("selected"))
    require("copy_only_operation", scope.get("operation") == "copy_if_absent", str(scope.get("operation")))
    require("no_overwrite", scope.get("overwrite") is False, str(scope.get("overwrite")))
    require("no_source_mutation", scope.get("source_mutation") is False, str(scope.get("source_mutation")))
    require("bounded_file_count", 0 < len(selected) <= 20, str(len(selected)))

    undo = _dict(change.get("undo"))
    require("undo_reversible", undo.get("reversible") is True, str(undo.get("reversible")))
    require("undo_source_restoration", undo.get("source_restoration_required") is False, str(undo.get("source_restoration_required")))

    normalized: list[dict[str, Any]] = []
    seen_targets: set[Path] = set()
    seen_names: set[str] = set()
    for position, item in enumerate(selected):
        if not isinstance(item, dict):
            errors.append(f"file_{position}_record: selected entry is not an object")
            continue
        source = _ref_path(item.get("source"), anchor=change_path)
        destination = _ref_path(item.get("target"), anchor=change_path)
        recorded_hash = item.get("sha256")
        recorded_bytes = item.get("bytes")
        require(f"file_{position}_source", bool(source and source.is_file()), str(source))
        require(
            f"file_{position}_source_worksite",
            bool(source and source_worksite and source.is_relative_to(source_worksite)),
            f"source={source} worksite={source_worksite}",
        )
        require(f"file_{position}_target_parent", bool(destination and target_dir and destination.parent == target_dir), str(destination))
        require(f"file_{position}_unique_target", bool(destination and destination not in seen_targets), str(destination))
        require(
            f"file_{position}_reserved_name",
            bool(destination and destination.name != "promotion-receipt.json"),
            str(destination.name if destination else None),
        )
        require(f"file_{position}_unique_name", bool(destination and destination.name not in seen_names), str(destination.name if destination else None))
        if destination:
            seen_targets.add(destination)
            seen_names.add(destination.name)
        actual_hash = _sha256(source) if source and source.is_file() else None
        actual_bytes = source.stat().st_size if source and source.is_file() else None
        require(f"file_{position}_source_hash", actual_hash == recorded_hash, f"expected={recorded_hash} actual={actual_hash}")
        require(f"file_{position}_source_bytes", actual_bytes == recorded_bytes, f"expected={recorded_bytes} actual={actual_bytes}")
        if source and destination:
            normalized.append({"source": source, "target": destination, "sha256": recorded_hash, "bytes": recorded_bytes})

    backup_status = (owner or {}).get("backup_status")
    change_backup_status = gates.get("managed_zone_backup_status")
    require("backup_status_binding", change_backup_status == backup_status, f"change_set={change_backup_status} live={backup_status}")
    require("backup_status_supported", backup_status in {"planned", "verified"}, str(backup_status))
    if backup_status == "planned":
        warnings.append("Managed Zone backup is planned; this apply is limited to preserved-source copy-only promotion.")

    expected_names = {item["target"].name for item in normalized} | {"promotion-receipt.json"}
    receipt_files = [
        {
            "name": item["target"].name,
            "source": str(item["source"]),
            "target": str(item["target"]),
            "sha256": item["sha256"],
            "bytes": item["bytes"],
        }
        for item in normalized
    ]

    def build_receipt(applied_at: str) -> dict[str, Any]:
        return {
            "schema": "aios.asset-promotion-receipt.v0",
            "status": "applied_validated",
            "asset_id": target.get("asset_id"),
            "asset_type": target.get("asset_type"),
            "owner_ref": owner_ref,
            "applied_at": applied_at,
            "change_set_id": change.get("id"),
            "change_set_path": str(change_path),
            "source_worksite": source_record,
            "matter_ref": change.get("matter_ref"),
            "assessment": change.get("assessment"),
            "files": receipt_files,
            "excluded": scope.get("excluded", []),
            "original_impact": "none; source Worksite and selected source files preserved",
            "backup_boundary": {
                "managed_zone_backup_status": backup_status,
                "allowed_scope": f"{len(receipt_files)}-file copy-only promotion with preserved independent source original",
                "does_not_authorize": ["move", "rename", "delete", "overwrite", "bulk curation", "source mutation"],
            },
            "undo": {
                "reversible": True,
                "guard": "Before deletion, require every file in this directory to match this receipt and its recorded SHA-256; then remove this target directory only.",
                "source_restoration_required": False,
            },
            "validation": {"verdict": "PASS", "checks": ["source hashes matched", "copy-if-absent used", "staged target hashes matched"]},
        }

    def existing_target_receipt() -> tuple[dict[str, Any] | None, list[str]]:
        existing_errors: list[str] = []
        if not target_dir or not target_dir.is_dir():
            return None, [f"target_existing_conflict: {target_dir}"]
        actual_names = {entry.name for entry in target_dir.iterdir()}
        if actual_names != expected_names:
            existing_errors.append(f"target_exact_set: expected={sorted(expected_names)} actual={sorted(actual_names)}")
        receipt_path = target_dir / "promotion-receipt.json"
        try:
            receipt = _load_json(receipt_path)
        except ValueError as exc:
            return None, [*existing_errors, str(exc)]
        checks = [
            ("receipt_schema", receipt.get("schema") in RECEIPT_SCHEMAS),
            ("receipt_status", receipt.get("status") == "applied_validated"),
            ("change_set_id", receipt.get("change_set_id") == change.get("id")),
            ("change_set_path", _ref_path(receipt.get("change_set_path"), anchor=receipt_path) == change_path),
            ("asset_id", receipt.get("asset_id") == target.get("asset_id")),
            ("asset_type", receipt.get("asset_type") == target.get("asset_type")),
            ("owner_ref", receipt.get("owner_ref") == owner_ref),
            ("source_worksite_id", _dict(receipt.get("source_worksite")).get("worksite_id") == source_record.get("worksite_id")),
            ("source_worksite_path", _ref_path(_dict(receipt.get("source_worksite")).get("worksite_path"), anchor=receipt_path) == source_worksite),
        ]
        for name, passed in checks:
            if not passed:
                existing_errors.append(f"{name}: existing receipt does not match pending change set")
        receipt_items = _list(receipt.get("files"))
        receipt_by_target = {
            str(_ref_path(item.get("target"), anchor=receipt_path)): item
            for item in receipt_items
            if isinstance(item, dict) and _ref_path(item.get("target"), anchor=receipt_path)
        }
        if len(receipt_items) != len(normalized):
            existing_errors.append(f"receipt_file_count: expected={len(normalized)} actual={len(receipt_items)}")
        for position, item in enumerate(normalized):
            installed = target_dir / item["target"].name
            receipt_item = receipt_by_target.get(str(item["target"]))
            if not installed.is_file():
                existing_errors.append(f"file_{position}_target: missing {installed}")
                continue
            if _sha256(installed) != item["sha256"] or installed.stat().st_size != item["bytes"]:
                existing_errors.append(f"file_{position}_target_hash: {installed}")
            if not receipt_item:
                existing_errors.append(f"file_{position}_receipt: missing {item['target']}")
            elif (
                _ref_path(receipt_item.get("source"), anchor=receipt_path) != item["source"]
                or receipt_item.get("sha256") != item["sha256"]
                or receipt_item.get("bytes") != item["bytes"]
            ):
                existing_errors.append(f"file_{position}_receipt_match: {item['target']}")
        return receipt, existing_errors

    base = {
        "schema": "aios.asset-promotion-apply.v1",
        "ok": not errors,
        "status": "planned" if not apply else "rejected",
        "change_set_path": str(change_path),
        "target_directory": str(target_dir) if target_dir else None,
        "selected_files": len(normalized),
        "errors": errors,
        "warnings": warnings,
    }
    if errors:
        return base

    def finalize_change(receipt: dict[str, Any]) -> dict[str, Any]:
        assert target_dir is not None
        receipt_path = target_dir / "promotion-receipt.json"
        updated = dict(change)
        updated["status"] = "applied_validated"
        updated["result"] = {
            "applied_at": receipt.get("applied_at"),
            "verdict": "PASS",
            "target_directory": str(target_dir),
            "promotion_receipt": str(receipt_path),
            "promotion_receipt_sha256": _sha256(receipt_path),
            "created_files": sorted(str(path) for path in target_dir.iterdir()),
            "source_files_unchanged": True,
        }
        try:
            _write_json_atomic(change_path, updated)
        except Exception as exc:
            return {**base, "ok": False, "status": "target_ready_change_set_pending", "errors": [f"change_set_finalize: {exc}"]}
        validation = validate_promotion(home, change_path, resolve_owner=resolve_owner, work_root=work_root)
        return {
            **base,
            "ok": validation["ok"],
            "status": "applied_validated" if validation["ok"] else "applied_validation_failed",
            "receipt_path": str(receipt_path),
            "validation": validation,
            "errors": validation.get("errors", []),
            "warnings": validation.get("warnings", warnings),
        }

    if target_dir and target_dir.exists():
        receipt, existing_errors = existing_target_receipt()
        if existing_errors or receipt is None:
            return {**base, "ok": False, "status": "target_exists_invalid", "errors": existing_errors}
        if not apply:
            return {**base, "ok": True, "status": "existing_target_ready_to_finalize", "errors": []}
        return finalize_change(receipt)

    if not apply:
        return base

    assert target_dir is not None
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target_dir.name}.promotion-", dir=str(target_dir.parent)))
    try:
        for item in normalized:
            staged_target = staging / item["target"].name
            shutil.copy2(item["source"], staged_target)
            if _sha256(staged_target) != item["sha256"] or staged_target.stat().st_size != item["bytes"]:
                raise ValueError(f"staged_copy_mismatch: {staged_target.name}")
        applied_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        receipt = build_receipt(applied_at)
        _write_json_atomic(staging / "promotion-receipt.json", receipt)
        _rename_directory_noreplace(staging, target_dir)
    except FileExistsError as exc:
        if staging.exists():
            shutil.rmtree(staging)
        return {**base, "ok": False, "status": "target_race_detected", "errors": [f"atomic_no_replace: {exc}"]}
    except Exception as exc:
        if staging.exists():
            shutil.rmtree(staging)
        return {**base, "ok": False, "status": "apply_failed", "errors": [str(exc)]}

    return finalize_change(receipt)


def _load_pair(path: Path) -> tuple[Path, dict[str, Any], Path, dict[str, Any]]:
    supplied = path.expanduser().resolve()
    record = _load_json(supplied)
    schema = record.get("schema")
    if schema in CHANGE_SET_SCHEMAS:
        change_path, change = supplied, record
        result = _dict(change.get("result"))
        receipt_path = _ref_path(result.get("promotion_receipt"), anchor=change_path)
        if receipt_path is None:
            raise ValueError("applied promotion change set does not reference a promotion receipt")
        receipt = _load_json(receipt_path)
    elif schema in RECEIPT_SCHEMAS:
        receipt_path, receipt = supplied, record
        change_path = _ref_path(receipt.get("change_set_path"), anchor=receipt_path)
        if change_path is None:
            raise ValueError("promotion receipt does not reference a change set")
        change = _load_json(change_path)
    else:
        raise ValueError(f"unsupported promotion schema: {schema!r}")
    return change_path, change, receipt_path, receipt


def validate_promotion(
    home: Path,
    supplied_path: Path,
    *,
    resolve_owner: Callable[[str], dict[str, Any] | None],
    work_root: Path,
) -> dict[str, Any]:
    """Validate one applied copy-only promotion without changing any file."""
    try:
        change_path, change, receipt_path, receipt = _load_pair(supplied_path)
    except ValueError as exc:
        return {
            "schema": "aios.asset-promotion-validation.v1",
            "ok": False,
            "validated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            "checks": [],
            "errors": [str(exc)],
            "warnings": [],
            "safe_to_remove_target_directory": False,
            "note": "Read-only validation failed before the promotion record pair could be resolved.",
        }

    checks: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(passed), "detail": detail})
        if not passed:
            errors.append(f"{name}: {detail}")

    check("change_set_schema", change.get("schema") in CHANGE_SET_SCHEMAS, str(change.get("schema")))
    check("receipt_schema", receipt.get("schema") in RECEIPT_SCHEMAS, str(receipt.get("schema")))
    check("change_set_status", change.get("status") == "applied_validated", str(change.get("status")))
    check("receipt_status", receipt.get("status") == "applied_validated", str(receipt.get("status")))
    check(
        "change_set_id",
        receipt.get("change_set_id") == change.get("id"),
        f"receipt={receipt.get('change_set_id')} change_set={change.get('id')}",
    )
    check(
        "change_set_path",
        _ref_path(receipt.get("change_set_path"), anchor=receipt_path) == change_path,
        str(change_path),
    )

    result = _dict(change.get("result"))
    check(
        "result_receipt_path",
        _ref_path(result.get("promotion_receipt"), anchor=change_path) == receipt_path,
        str(receipt_path),
    )
    actual_receipt_hash = _sha256(receipt_path)
    check(
        "receipt_sha256",
        result.get("promotion_receipt_sha256") == actual_receipt_hash,
        f"expected={result.get('promotion_receipt_sha256')} actual={actual_receipt_hash}",
    )

    target = _dict(change.get("target"))
    target_dir = _ref_path(target.get("directory"), anchor=change_path)
    check("target_directory", bool(target_dir and target_dir.is_dir()), str(target_dir))
    check("receipt_location", bool(target_dir and receipt_path.parent == target_dir), str(receipt_path))

    check("asset_id", bool(receipt.get("asset_id")) and receipt.get("asset_id") == target.get("asset_id"), f"receipt={receipt.get('asset_id')} change_set={target.get('asset_id')}")
    check("asset_type", bool(receipt.get("asset_type")) and receipt.get("asset_type") == target.get("asset_type"), f"receipt={receipt.get('asset_type')} change_set={target.get('asset_type')}")

    change_source = _dict(change.get("source"))
    receipt_source = _dict(receipt.get("source_worksite"))
    source_worksite = _ref_path(receipt_source.get("worksite_path"), anchor=receipt_path)
    change_worksite = _ref_path(change_source.get("worksite_path"), anchor=change_path)
    check("source_worksite_id", bool(receipt_source.get("worksite_id")) and receipt_source.get("worksite_id") == change_source.get("worksite_id"), f"receipt={receipt_source.get('worksite_id')} change_set={change_source.get('worksite_id')}")
    check("source_worksite_path", bool(source_worksite) and source_worksite == change_worksite, f"receipt={source_worksite} change_set={change_worksite}")

    receipt_owner_ref = receipt.get("owner_ref")
    change_owner_ref = target.get("owner_ref")
    check("owner_ref_present", isinstance(receipt_owner_ref, str) and receipt_owner_ref.startswith("source:"), str(receipt_owner_ref))
    check("owner_ref_binding", receipt_owner_ref == change_owner_ref, f"receipt={receipt_owner_ref} change_set={change_owner_ref}")
    owner_ref = receipt_owner_ref if isinstance(receipt_owner_ref, str) else ""
    owner_id = owner_ref.removeprefix("source:") if owner_ref.startswith("source:") else ""
    owner = resolve_owner(owner_id) if owner_id else None
    owner_record = owner or {}
    check("owner_resolves", bool(owner) and owner_ref == f"source:{owner_id}", str(owner_ref))
    check("owner_kind", bool(owner) and owner_record.get("kind") == "managed_zone", str(owner_record.get("kind")))
    check(
        "owner_access",
        bool(owner) and owner_record.get("access_mode") == "curate_reversible",
        str(owner_record.get("access_mode")),
    )
    locations = _list(owner_record.get("locations"))
    local_locations = [
        item for item in locations
        if isinstance(item, dict) and item.get("kind") == "local" and item.get("path")
    ]
    managed_root: Path | None = None
    if local_locations:
        raw_root = str(local_locations[0]["path"])
        managed_root = (home / raw_root[2:] if raw_root.startswith("~/") else Path(os.path.expandvars(raw_root)).expanduser()).resolve()
    managed_dir = (managed_root / "managed").resolve() if managed_root else None
    contained = bool(target_dir and managed_dir and target_dir.is_relative_to(managed_dir) and target_dir != managed_dir)
    check("target_containment", contained, f"target={target_dir} managed={managed_dir}")

    scope = _dict(change.get("scope"))
    selected = _list(scope.get("selected"))
    copy_only = (
        scope.get("operation") == "copy_if_absent"
        and scope.get("overwrite") is False
        and scope.get("source_mutation") is False
    )
    check(
        "copy_only_operation",
        copy_only,
        json.dumps({key: scope.get(key) for key in ("operation", "overwrite", "source_mutation")}),
    )
    check("bounded_file_count", 0 < len(selected) <= 20, str(len(selected)))

    receipt_files = _list(receipt.get("files"))
    check(
        "receipt_file_count",
        len(receipt_files) == len(selected) and bool(receipt_files),
        f"receipt={len(receipt_files)} selected={len(selected)}",
    )
    selected_by_target: dict[str, dict[str, Any]] = {}
    for item in selected:
        if not isinstance(item, dict):
            continue
        target_path = _ref_path(item.get("target"), anchor=change_path)
        if target_path:
            selected_by_target[str(target_path)] = item

    expected_entries = {receipt_path.name}
    seen_targets: set[str] = set()
    resolved_work_root = work_root.resolve()

    for position, item in enumerate(receipt_files):
        if not isinstance(item, dict):
            check(f"file_{position}_record", False, "receipt file entry is not an object")
            continue
        source = _ref_path(item.get("source"), anchor=receipt_path)
        target_path = _ref_path(item.get("target"), anchor=receipt_path)
        recorded_hash = item.get("sha256")
        recorded_bytes = item.get("bytes")
        expected_entries.add(target_path.name if target_path else f"<missing-{position}>")
        check(f"file_{position}_source", bool(source and source.is_file()), str(source))
        check(f"file_{position}_target", bool(target_path and target_path.is_file()), str(target_path))
        check(
            f"file_{position}_target_parent",
            bool(target_path and target_dir and target_path.parent == target_dir),
            str(target_path),
        )
        check(
            f"file_{position}_unique_target",
            bool(target_path and str(target_path) not in seen_targets),
            str(target_path),
        )
        if target_path:
            seen_targets.add(str(target_path))
        source_hash = _sha256(source) if source and source.is_file() else None
        target_hash = _sha256(target_path) if target_path and target_path.is_file() else None
        check(f"file_{position}_source_hash", source_hash == recorded_hash, f"expected={recorded_hash} actual={source_hash}")
        check(f"file_{position}_target_hash", target_hash == recorded_hash, f"expected={recorded_hash} actual={target_hash}")
        target_bytes = target_path.stat().st_size if target_path and target_path.is_file() else None
        check(f"file_{position}_bytes", target_bytes == recorded_bytes, f"expected={recorded_bytes} actual={target_bytes}")
        selected_item = selected_by_target.get(str(target_path)) if target_path else None
        selected_source = _ref_path(selected_item.get("source"), anchor=change_path) if isinstance(selected_item, dict) else None
        selected_matches = (
            bool(selected_item)
            and source == selected_source
            and selected_item.get("sha256") == recorded_hash
            and selected_item.get("bytes") == recorded_bytes
        )
        check(f"file_{position}_change_set_match", selected_matches, str(target_path))
        source_in_worksite = bool(
            source
            and source_worksite
            and source.is_relative_to(source_worksite)
            and source_worksite.is_relative_to(resolved_work_root)
        )
        check(
            f"file_{position}_source_worksite",
            source_in_worksite,
            f"source={source} worksite={source_worksite}",
        )

    actual_entries = {entry.name for entry in target_dir.iterdir()} if target_dir and target_dir.is_dir() else set()
    check(
        "target_exact_set",
        actual_entries == expected_entries,
        f"expected={sorted(expected_entries)} actual={sorted(actual_entries)}",
    )
    created_files = _list(result.get("created_files"))
    created_set = {str(_ref_path(item, anchor=change_path)) for item in created_files}
    expected_created_set = {str(target_dir / name) for name in expected_entries} if target_dir else set()
    check(
        "result_created_files",
        created_set == expected_created_set,
        f"expected={sorted(expected_created_set)} actual={sorted(created_set)}",
    )
    check("result_source_unchanged", result.get("source_files_unchanged") is True, str(result.get("source_files_unchanged")))

    backup_status = owner_record.get("backup_status")
    boundary = _dict(receipt.get("backup_boundary"))
    gates = _dict(change.get("gates"))
    receipt_backup_status = boundary.get("managed_zone_backup_status")
    change_backup_status = gates.get("managed_zone_backup_status")
    check("receipt_backup_status", receipt_backup_status == backup_status, f"receipt={receipt_backup_status} live={backup_status}")
    check("change_set_backup_status", change_backup_status == backup_status, f"change_set={change_backup_status} live={backup_status}")
    if backup_status == "verified":
        check("backup_boundary", True, "backup_status=verified")
    else:
        allowed_scope = str(boundary.get("allowed_scope", ""))
        prohibited = {str(item) for item in _list(boundary.get("does_not_authorize"))}
        required_prohibitions = {"move", "rename", "delete", "overwrite", "bulk curation", "source mutation"}
        check("backup_prohibitions", required_prohibitions.issubset(prohibited), f"required={sorted(required_prohibitions)} actual={sorted(prohibited)}")
        waiver_ok = backup_status == "planned" and "copy-only" in allowed_scope and copy_only and result.get("source_files_unchanged") is True
        check("backup_boundary", waiver_ok, f"backup_status={backup_status} allowed_scope={allowed_scope!r}")
        if waiver_ok:
            warnings.append(
                "Managed Zone backup is planned; this validates only a preserved-source copy-only promotion "
                "and does not authorize move/delete/overwrite/bulk curation."
            )

    receipt_undo = _dict(receipt.get("undo"))
    change_undo = _dict(change.get("undo"))
    check("undo_reversible", receipt_undo.get("reversible") is True and change_undo.get("reversible") is True, f"receipt={receipt_undo.get('reversible')} change_set={change_undo.get('reversible')}")
    check("undo_source_restoration", receipt_undo.get("source_restoration_required") is False and change_undo.get("source_restoration_required") is False, f"receipt={receipt_undo.get('source_restoration_required')} change_set={change_undo.get('source_restoration_required')}")

    ok = not errors
    return {
        "schema": "aios.asset-promotion-validation.v1",
        "ok": ok,
        "validated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "change_set_path": str(change_path),
        "receipt_path": str(receipt_path),
        "target_directory": str(target_dir) if target_dir else None,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "safe_to_remove_target_directory": ok,
        "note": (
            "Read-only validation. safe_to_remove_target_directory is a hash/exact-set precondition, "
            "not permission and not an automatic delete action."
        ),
    }
