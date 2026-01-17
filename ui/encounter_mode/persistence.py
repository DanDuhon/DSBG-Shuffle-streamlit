from pathlib import Path
from typing import Any, Dict
import json
import os


DATA_DIR = Path("data")
SAVED_ENCOUNTERS_PATH = DATA_DIR / "saved_encounters.json"


def load_saved_encounters(*, reload: bool = False) -> Dict[str, Any]:
    if not SAVED_ENCOUNTERS_PATH.exists():
        return {}
    with SAVED_ENCOUNTERS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return {}
    return data


def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        os.replace(str(tmp), str(path))
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def save_saved_encounters(encounters: Dict[str, Any]) -> None:
    _atomic_write(SAVED_ENCOUNTERS_PATH, encounters)
