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


def parse_stable_key(filename: str, vendor: str) -> str:
    """Extract a stable dataset identity from a raw input filename.

    Fugro:  ``4424-260484_HHW_normaal_01-01-2024 …_Uur_2026….csv``
            → ``4424-260484_HHW_normaal_Uur``
    Wiertsema: ``Beemster_86349_1_deel_1.xlsx`` → ``Beemster_86349_1``
    """
    stem = Path(filename).stem
    vendor_lower = vendor.lower()

    if vendor_lower == "fugro":
        # Match the date-range block: dd-mm-yyyy ...
        m = re.match(
            r"^(.+?)_(\d{2}-\d{2}-\d{4}\s.+?_(Uur|Dag|Maand)_\d+)$",
            stem,
        )
        if m:
            prefix = m.group(1)
            interval = m.group(3)
            return f"{prefix}_{interval}"
        return stem

    if vendor_lower == "wiertsema":
        return re.sub(r"_deel_\d+$", "", stem)

    return stem


def match_origin_folder(
    stable_key: str,
    vendor: str,
    output_dir: Path,
) -> str | None:
    """Find an existing origin folder whose stable key matches *stable_key*."""
    vendor_dir = output_dir / vendor.lower()
    if not vendor_dir.is_dir():
        return None
    for d in vendor_dir.iterdir():
        if d.is_dir() and parse_stable_key(d.name, vendor) == stable_key:
            return d.name
    return None


def resolve_dataset_root(dataset: str, repo_root: Path) -> Path:
    dataset = dataset.lower()
    if dataset not in ("fugro", "wiertsema"):
        raise ValueError(f"dataset must be 'fugro' or 'wiertsema', got '{dataset}'")
    return repo_root / "output_data" / dataset
