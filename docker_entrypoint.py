import os
import shutil
import sys
from pathlib import Path


def _copy_tree_missing_only(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)

    for item in source_dir.iterdir():
        dest = target_dir / item.name
        if dest.exists():
            continue

        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


def seed_persistent_data_if_needed() -> None:
    seed_dir = Path(os.getenv("DSBG_SEED_DATA_DIR", "/opt/seed/data"))
    data_dir = Path(os.getenv("DSBG_DATA_DIR", "/app/data"))

    # Marker file: if present, assume the data volume has already been initialized.
    marker_file = data_dir / os.getenv("DSBG_DATA_MARKER", "bosses.json")

    if marker_file.exists():
        return

    if not seed_dir.exists():
        print(
            f"[dsbg] Seed directory missing: {seed_dir}. "
            "Container image may be incomplete.",
            file=sys.stderr,
        )
        return

    print(f"[dsbg] Initializing persistent data volume at {data_dir}...")
    _copy_tree_missing_only(seed_dir, data_dir)


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
