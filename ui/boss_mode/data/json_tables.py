from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_JSON_CACHE: dict[Path, tuple[int, Any]] = {}


def _to_tuples(value: Any) -> Any:
    if isinstance(value, list):
        # Interpret [x, y] as a coordinate tuple.
        if (
            len(value) == 2
            and isinstance(value[0], int)
            and isinstance(value[1], int)
        ):
            return (value[0], value[1])
        return [_to_tuples(v) for v in value]

    if isinstance(value, dict):
        return {k: _to_tuples(v) for k, v in value.items()}

    return value


def _load_json_mtime_cached(path: Path) -> Any:
    try:
        mtime_ns = path.stat().st_mtime_ns
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Boss Mode JSON table not found: {path}. "
            "Run from repo root so relative data/ paths resolve."
        ) from exc

    cached = _JSON_CACHE.get(path)
    if cached and cached[0] == mtime_ns:
        return cached[1]

    data = json.loads(path.read_text(encoding="utf-8"))
    data = _to_tuples(data)
    _JSON_CACHE[path] = (mtime_ns, data)
    return data


@dataclass(frozen=True)
class LazyJsonSequence(Sequence[Any]):
    path: Path
    decoder: Callable[[Any], Any] | None = None

    def _value(self) -> Any:
        value = _load_json_mtime_cached(self.path)
        if self.decoder:
            value = self.decoder(value)
        return value

    def __len__(self) -> int:
        return len(self._value())

    def __getitem__(self, index):
        return self._value()[index]

    def __iter__(self):
        return iter(self._value())


def boss_mode_data_path(*parts: str) -> Path:
    return Path("data") / "boss_mode" / Path(*parts)
