"""Guard the fixed CLI artifact names when an output directory is reused."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

NAMES = (
    "result.json",
    "witness.json",
    "replay.sql",
    "invalid_candidate.json",
    "invalid_candidate.sql",
)
MARKER = ".dataproof-owned.json"


class ArtifactConflict(ValueError):
    """An output path cannot be safely reused without risking user files."""


def _digest(path: Path) -> str:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ArtifactConflict(f"artifact is not a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(directory: Path, files: dict[str, str]) -> None:
    payload = json.dumps({"schema_version": 1, "files": files}, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix=".dataproof-owned-", dir=directory, delete=False
    ) as stream:
        temp = Path(stream.name)
        stream.write(payload)
    try:
        os.replace(temp, directory / MARKER)
    finally:
        temp.unlink(missing_ok=True)


def prepare(directory: Path) -> None:
    """Clear only unchanged files recorded by an earlier DataProof run."""
    if directory.is_symlink():
        raise ArtifactConflict(f"output directory is a symlink: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / MARKER
    owned: dict[str, str] = {}
    if marker.exists() or marker.is_symlink():
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ArtifactConflict("invalid DataProof ownership record") from exc
        if (
            not stat.S_ISREG(marker.lstat().st_mode)
            or not isinstance(data, dict)
            or data.get("schema_version") != 1
            or not isinstance(data.get("files"), dict)
            or any(
                name not in NAMES or not isinstance(digest, str) or len(digest) != 64
                for name, digest in data["files"].items()
            )
        ):
            raise ArtifactConflict("invalid DataProof ownership record")
        owned = data["files"]
    for name in NAMES:
        path = directory / name
        present = path.exists() or path.is_symlink()
        if present and (name not in owned or _digest(path) != owned[name]):
            raise ArtifactConflict(f"unowned or modified artifact: {path}")
    for name in owned:
        (directory / name).unlink(missing_ok=True)
    _record(directory, {})


def finish(directory: Path, *, success_status: str = "COUNTEREXAMPLE_FOUND") -> None:
    """Publish ownership only for this run's completed outputs."""
    result_path = directory / "result.json"
    if not result_path.exists():
        for name in NAMES:
            (directory / name).unlink(missing_ok=True)
        _record(directory, {})
        return
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != success_status:
        for name in ("witness.json", "replay.sql"):
            (directory / name).unlink(missing_ok=True)
    owned = {name: _digest(directory / name) for name in NAMES if (directory / name).exists()}
    if (
        result.get("status") == success_status
        and not {"witness.json", "replay.sql"} <= owned.keys()
    ):
        raise ArtifactConflict("successful result is missing witness or replay SQL")
    _record(directory, owned)
