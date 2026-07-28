import re
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    p = (start or Path.cwd()).resolve()
    for candidate in [p] + list(p.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return p


def sanitize_for_filename(name: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(name))
    safe = safe.strip(" ._")
    return safe or "series"


def get_series_base(stem: str) -> str:
    return re.sub(r"_sensor_\d+$", "", stem)


def group_sensor_files(csv_files: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for p in csv_files:
        base = get_series_base(p.stem)
        groups.setdefault(base, []).append(p)
    for base in groups:
        groups[base].sort()
    return groups


def resolve_dataset_root(dataset: str, repo_root: Path) -> Path:
    dataset = dataset.lower()
    if dataset not in ("fugro", "wiertsema"):
        raise ValueError(f"dataset must be 'fugro' or 'wiertsema', got '{dataset}'")
    return repo_root / "output_data" / dataset
