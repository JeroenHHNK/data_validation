"""Derive OBJECT_DATA.csv from the standardized only_csv filenames.

Runs *after* the renaming step, so filenames are already in their final form.
Fugro and Wiertsema have genuinely different conventions and therefore get
separate parsers; they share only the cross-section code vocabulary and the
grouping/dedup logic.

Fugro
    ``NL-253677-FB-FLB5073_HB-SS060_BIT_PB1_-4.7_-5.7_m_NAP_avg``
    The two numbers before the ``_m_NAP[_avg]`` suffix are top/bottom of the
    filter; the deeper one is ``bottom_filter``.

Wiertsema
    ``86349-1 MB049PB01 B_BE0377+32_BIKR_GMW_PB1_F-252``
    The trailing ``F-<n>`` token is the filter *midpoint*; filters are 1.0 m
    long, so ``bottom_filter = midpoint - 0.5``. The token is written either in
    metres (``F-6.10``) or in centimetres (``F-252`` -> -2.52, ``F-398.5`` ->
    -3.985); magnitude disambiguates them (see ``_MIDPOINT_CM_THRESHOLD``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from dataval._utils import get_series_base

#: Cross-section codes, ordered outer -> inner across the dike transect.
#: ``BIB`` (binnenberm) mirrors ``BUB`` (buitenberm); it is absent from some
#: older code lists but occurs throughout the delivered data.
CROSS_SEC_CODES: tuple[str, ...] = (
    "KRBUB", "BUB", "INBUB", "BUKR", "KR", "BIKR", "INBIB", "KRBIB", "BIT", "BIB",
)

#: ``F-`` tokens at or above this magnitude are centimetres, below it metres.
#: Real data: metre tokens span 2.76-19.95, centimetre tokens span 188-2096,
#: so any threshold in (20, 188) separates them cleanly.
_MIDPOINT_CM_THRESHOLD = 20.0

#: Filters are 1.0 m long, so the bottom sits half a metre below the midpoint.
_FILTER_HALF_LENGTH_M = 0.5

#: Structural tokens that are never a cross-section code.
_NON_CODE_TOKENS = {"GMW", "PB", "HB", "MB", "NAP", "DP", "M"}

_SENSOR_RE = re.compile(r"_sensor_(\d+)$")
_FUGRO_TAIL_RE = re.compile(
    r"^(?P<base>.*?)_(?P<top>-?\d+(?:\.\d+)?)_(?P<bottom>-?\d+(?:\.\d+)?)$"
)
_WIERTSEMA_F_RE = re.compile(r"^(?P<base>.*)_F-(?P<value>\d+(?:\.\d+)?)$")
#: Windows "- Copy" export duplicates, which sit between the filter pair and
#: the unit suffix and would otherwise hide the filter values.
_FUGRO_COPY_RE = re.compile(r"_-_Copy(?:_\d+)?$", re.IGNORECASE)
_HAS_DIGIT_RE = re.compile(r"\d")


@dataclass
class ParsedFile:
    """One physical sensor file, parsed into object metadata."""

    stem: str
    name_timeseries: str
    bottom_filter: float | None = None
    top_filter: float | None = None
    cross_sec_location: str | None = None
    cross_sec_known: bool = True
    sensor: int | None = None
    is_nap: bool = True
    notes: list[str] = field(default_factory=list)


def _split_sensor(stem: str) -> tuple[str, int | None]:
    """Return (stem without ``_sensor_N``, sensor number or None)."""
    m = _SENSOR_RE.search(stem)
    if not m:
        return stem, None
    return get_series_base(stem), int(m.group(1))


def _tokenize(text: str) -> list[str]:
    """Split a descriptor into candidate code tokens on underscores/spaces."""
    return [t for t in re.split(r"[_\s]+", text) if t]


def _match_known_code(tokens: list[str]) -> str | None:
    """Return the known cross-section code among *tokens*, if any.

    Matching is on whole tokens, so ``BIKR`` never matches as ``KR``.
    """
    hits = [t for t in tokens if t.upper() in CROSS_SEC_CODES]
    if not hits:
        return None
    return hits[-1].upper()


# --------------------------------------------------------------------------
# Fugro
# --------------------------------------------------------------------------

def parse_fugro_filename(stem: str) -> ParsedFile:
    """Parse a Fugro only_csv stem into object metadata."""
    base, sensor = _split_sensor(stem)

    body = base
    is_nap = True
    if body.endswith("_avg"):
        body = body[: -len("_avg")]
    if body.endswith("_m_NAP"):
        body = body[: -len("_m_NAP")]
    else:
        # e.g. ``NL-241417-ET-19121810_Waterstand_cmH2O`` -- surface water in
        # centimetres, not a piezometer. No filter, and the metre-based rules
        # do not apply.
        is_nap = False

    parsed = ParsedFile(stem=stem, name_timeseries=body, sensor=sensor, is_nap=is_nap)

    if not is_nap:
        parsed.name_timeseries = base
        parsed.notes.append("not an m NAP series; no filter, flagging skipped")
        return parsed

    body, n_copy = _FUGRO_COPY_RE.subn("", body)
    if n_copy:
        parsed.notes.append("duplicate '- Copy' export; verify against the original")

    m = _FUGRO_TAIL_RE.match(body)
    if m:
        top = float(m.group("top"))
        bottom = float(m.group("bottom"))
        parsed.name_timeseries = m.group("base")
        # The spec's rule is "the second is the bottom"; guard against a
        # reversed pair rather than silently trusting the order.
        if bottom > top:
            parsed.notes.append(
                f"filter pair not descending ({top} then {bottom}); used the deeper value"
            )
        parsed.top_filter = max(top, bottom)
        parsed.bottom_filter = min(top, bottom)
    else:
        parsed.notes.append("no top/bottom filter pair found in filename")

    _assign_cross_sec(parsed, parsed.name_timeseries)
    return parsed


# --------------------------------------------------------------------------
# Wiertsema
# --------------------------------------------------------------------------

def midpoint_from_f_token(token: str) -> float:
    """Convert an ``F-`` token to a filter midpoint in m NAP (always negative).

    ``"252"`` -> -2.52, ``"398.5"`` -> -3.985, ``"6.10"`` -> -6.10.
    """
    value = float(token)
    if value >= _MIDPOINT_CM_THRESHOLD:
        value /= 100.0
    return -value


def parse_wiertsema_filename(stem: str) -> ParsedFile:
    """Parse a Wiertsema only_csv stem into object metadata."""
    base, sensor = _split_sensor(stem)
    parsed = ParsedFile(stem=stem, name_timeseries=base, sensor=sensor)

    m = _WIERTSEMA_F_RE.match(base)
    if m:
        midpoint = midpoint_from_f_token(m.group("value"))
        parsed.name_timeseries = m.group("base")
        parsed.top_filter = midpoint + _FILTER_HALF_LENGTH_M
        parsed.bottom_filter = midpoint - _FILTER_HALF_LENGTH_M
    else:
        parsed.notes.append("no F- filter token in filename")

    _assign_cross_sec(parsed, parsed.name_timeseries)
    return parsed


# --------------------------------------------------------------------------
# Shared cross-section handling
# --------------------------------------------------------------------------

def _cross_sec_fallback(descriptor: str) -> str | None:
    """Best-effort code extraction when no known code is present.

    Wiertsema names read ``<location>_<CODE>_GMW_PB<n>``; the code is whatever
    sits between the location token and ``GMW``, which keeps multi-token codes
    such as ``INST_B`` intact. Without ``GMW``, fall back to the trailing
    alphabetic token.
    """
    tokens = _tokenize(descriptor)
    upper = [t.upper() for t in tokens]

    if "GMW" in upper:
        gmw = upper.index("GMW")
        start = 0
        for i in range(gmw - 1, -1, -1):
            if _HAS_DIGIT_RE.search(tokens[i]):
                start = i + 1
                break
        candidate = "_".join(tokens[start:gmw]).upper()
        if candidate and candidate not in _NON_CODE_TOKENS:
            return candidate

    for tok in reversed(tokens):
        if tok.isalpha() and 2 <= len(tok) <= 7 and tok.upper() not in _NON_CODE_TOKENS:
            return tok.upper()
    return None


def _assign_cross_sec(parsed: ParsedFile, descriptor: str) -> None:
    code = _match_known_code(_tokenize(descriptor))
    if code is not None:
        parsed.cross_sec_location = code
        parsed.cross_sec_known = True
        return

    candidate = _cross_sec_fallback(descriptor)
    if candidate:
        # Keep the text rather than discarding it, but mark it for review.
        parsed.cross_sec_location = candidate
        parsed.cross_sec_known = False
        parsed.notes.append(f"cross-section code '{candidate}' outside the known set")
    else:
        parsed.cross_sec_location = None
        parsed.cross_sec_known = True


PARSERS = {"fugro": parse_fugro_filename, "wiertsema": parse_wiertsema_filename}


def parse_filename(stem: str, vendor: str) -> ParsedFile:
    """Dispatch to the vendor-specific parser."""
    try:
        parser = PARSERS[vendor.lower()]
    except KeyError:
        raise ValueError(f"vendor must be 'fugro' or 'wiertsema', got '{vendor}'")
    return parser(stem)


# --------------------------------------------------------------------------
# Building OBJECT_DATA.csv
# --------------------------------------------------------------------------

OBJECT_DATA_FILENAME = "OBJECT_DATA.csv"

#: Required columns first, provenance/review columns after.
OBJECT_DATA_COLUMNS = [
    "name_timeseries",
    "bottom_filter",
    "cross_sec_location",
    "top_filter",
    "n_sensor_files",
    "source_files",
    "is_nap",
    "needs_review",
    "review_reason",
]


def list_only_csv(project_dir):
    """Return the sorted only_csv files for a project folder."""
    only_csv = project_dir / "only_csv"
    if not only_csv.is_dir():
        return []
    return sorted(only_csv.glob("*.csv"))


def _unique(values):
    """Distinct non-null values, order preserved."""
    out = []
    for v in values:
        if v is None:
            continue
        if v not in out:
            out.append(v)
    return out


def build_object_data(project_dir, vendor):
    """Build the object table for one project folder.

    One row per ``name_timeseries``: sensor files that stitch into a single
    logical series are collapsed into one row. Where a group disagrees on
    ``bottom_filter`` or ``cross_sec_location`` the row is flagged for manual
    review rather than silently picking one value.
    """
    import pandas as pd

    parsed = [parse_filename(p.stem, vendor) for p in list_only_csv(project_dir)]

    groups = {}
    for item in parsed:
        groups.setdefault(item.name_timeseries, []).append(item)

    rows = []
    for name, items in groups.items():
        reasons = []

        bottoms = _unique([i.bottom_filter for i in items])
        tops = _unique([i.top_filter for i in items])
        codes = _unique([i.cross_sec_location for i in items])

        if len(bottoms) > 1:
            reasons.append(
                "sensor files disagree on bottom_filter: "
                + ", ".join(f"{b:g}" for b in bottoms)
            )
        if len(codes) > 1:
            reasons.append(
                "sensor files disagree on cross_sec_location: " + ", ".join(codes)
            )
        if any(not i.cross_sec_known for i in items):
            reasons.extend(_unique([n for i in items for n in i.notes if "outside the known set" in n]))
        for note in _unique([n for i in items for n in i.notes if "outside the known set" not in n]):
            reasons.append(note)

        # A disputed value is left empty so nothing downstream trusts a guess.
        bottom = bottoms[0] if len(bottoms) == 1 else None
        top = tops[0] if len(tops) == 1 else None
        code = codes[0] if len(codes) == 1 else None

        rows.append({
            "name_timeseries": name,
            "bottom_filter": bottom,
            "cross_sec_location": code,
            "top_filter": top,
            "n_sensor_files": len(items),
            "source_files": ";".join(sorted(i.stem for i in items)),
            "is_nap": all(i.is_nap for i in items),
            "needs_review": bool(reasons),
            "review_reason": "; ".join(reasons),
        })

    df = pd.DataFrame(rows, columns=OBJECT_DATA_COLUMNS)
    if not df.empty:
        df = df.sort_values("name_timeseries").reset_index(drop=True)
    return df


def write_object_data(project_dir, vendor):
    """Build and write ``OBJECT_DATA.csv`` into *project_dir*. Returns the frame."""
    df = build_object_data(project_dir, vendor)
    out_path = project_dir / OBJECT_DATA_FILENAME
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    return df, out_path


def load_object_data(project_dir):
    """Read a project's OBJECT_DATA.csv, or None when it has not been built."""
    import pandas as pd

    path = project_dir / OBJECT_DATA_FILENAME
    if not path.exists():
        return None
    return pd.read_csv(path, encoding="utf-8-sig", encoding_errors="replace")


def bottom_filter_map(project_dir):
    """Map ``name_timeseries`` -> bottom_filter (float), skipping missing values."""
    import pandas as pd

    df = load_object_data(project_dir)
    if df is None or df.empty:
        return {}
    out = {}
    for _, row in df.iterrows():
        value = pd.to_numeric(row.get("bottom_filter"), errors="coerce")
        if pd.notna(value):
            out[str(row["name_timeseries"])] = float(value)
    return out
