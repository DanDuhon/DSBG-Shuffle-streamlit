import hashlib
import json
import os
import shutil
import sys
from pathlib import Path


MANIFEST_NAME = ".dsbg_seed_manifest.json"


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sync_tree(seed_dir: Path, data_dir: Path, prior: dict[str, str]) -> dict[str, str]:
    """Copy seed content into the data volume, preserving user edits.

    A file is written when it is new, or when it still matches the digest we
    recorded the last time we seeded it (i.e. the user has not modified it).
    Returns the manifest for this seed pass.
    """
    manifest: dict[str, str] = {}

    for src in sorted(seed_dir.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(seed_dir).as_posix()
        dest = data_dir / rel
        new_digest = _digest(src)
        manifest[rel] = new_digest

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            continue

        if _digest(dest) == new_digest:
            continue  # already current

        if prior.get(rel) is not None and _digest(dest) == prior[rel]:
            shutil.copy2(src, dest)  # untouched by the user; safe to update
        else:
            print(f"[dsbg] Keeping user-modified {rel}; seed version not applied.",
                  file=sys.stderr)

    return manifest


def seed_persistent_data_if_needed() -> None:
    seed_dir = Path(os.getenv("DSBG_SEED_DATA_DIR", "/opt/seed/data"))
    data_dir = Path(os.getenv("DSBG_DATA_DIR", "/app/data"))

    if not seed_dir.exists():
        print(f"[dsbg] Seed directory missing: {seed_dir}. "
              "Container image may be incomplete.", file=sys.stderr)
        return

    data_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = data_dir / MANIFEST_NAME

    prior: dict[str, str] = {}
    if manifest_path.exists():
        try:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            print("[dsbg] Unreadable seed manifest; treating all files as user-modified.",
                  file=sys.stderr)

    manifest = _sync_tree(seed_dir, data_dir, prior)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def main() -> None:
    seed_persistent_data_if_needed()

    port = os.getenv("STREAMLIT_SERVER_PORT", "8501")
    address = os.getenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")

    args = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app.py",
        "--server.port",
        str(port),
        "--server.address",
        str(address),
    ]

    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
