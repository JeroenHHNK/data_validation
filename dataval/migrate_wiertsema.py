"""Migrate existing wiertsema output folders to stable-key naming.

Dry-run by default — prints a table of planned operations without touching disk.
Pass ``--apply`` to execute the migration.

Usage::

    poetry run python -m dataval.migrate_wiertsema
    poetry run python -m dataval.migrate_wiertsema --apply
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from ._utils import find_repo_root, normalize_wiertsema_key, stable_key_from_csvs


def _derive_key(folder: Path) -> str | None:
    """Derive stable key from folder name, falling back to CSV filenames."""
    key = normalize_wiertsema_key(folder.name)
    if key:
        return key
    return stable_key_from_csvs(folder)


def _collect_plans(
    wiertsema_dir: Path,
) -> tuple[list[dict], list[dict]]:
    """Scan folders and build a migration plan.

    Returns (plans, unresolvable) where each plan is a dict with
    source, target, key, file_count, and conflict info.
    """
    if not wiertsema_dir.is_dir():
        return [], []

    folders = sorted(
        d for d in wiertsema_dir.iterdir()
        if d.is_dir()
    )

    plans: list[dict] = []
    unresolvable: list[dict] = []

    for folder in folders:
        key = _derive_key(folder)
        if key is None:
            unresolvable.append({
                "source": folder.name,
                "reason": "Could not derive stable key from folder name or CSV filenames",
            })
            continue

        if folder.name == key:
            continue

        all_files = []
        for item in folder.rglob("*"):
            if item.is_file():
                all_files.append(item.relative_to(folder))

        plans.append({
            "source": folder.name,
            "target": key,
            "key": key,
            "file_count": len(all_files),
            "files": all_files,
        })

    return plans, unresolvable


def _detect_conflicts(plans: list[dict], wiertsema_dir: Path) -> list[dict]:
    """Annotate plans with merge conflict info where multiple sources share a target."""
    target_groups: dict[str, list[dict]] = {}
    for plan in plans:
        target_groups.setdefault(plan["target"], []).append(plan)

    for target, group in target_groups.items():
        target_dir = wiertsema_dir / target
        all_sources = [p["source"] for p in group]
        if target_dir.is_dir() and target_dir.name not in all_sources:
            all_sources.insert(0, target_dir.name)

        for plan in group:
            plan["merge_with"] = [s for s in all_sources if s != plan["source"]]

    # Check for filename collisions within merges
    for target, group in target_groups.items():
        target_dir = wiertsema_dir / target
        existing_files: dict[str, Path] = {}
        if target_dir.is_dir():
            for item in target_dir.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(target_dir)
                    existing_files[str(rel)] = item

        for plan in group:
            conflicts = []
            source_dir = wiertsema_dir / plan["source"]
            for rel_path in plan["files"]:
                key_str = str(rel_path)
                if key_str in existing_files:
                    src_file = source_dir / rel_path
                    dst_file = existing_files[key_str]
                    src_mtime = src_file.stat().st_mtime
                    dst_mtime = dst_file.stat().st_mtime
                    conflicts.append({
                        "file": key_str,
                        "src_newer": src_mtime > dst_mtime,
                    })
                existing_files[key_str] = source_dir / rel_path
            plan["conflicts"] = conflicts

    return plans


def _apply_migration(
    plans: list[dict],
    wiertsema_dir: Path,
    log_path: Path,
) -> list[dict]:
    """Execute the migration. Returns the log entries."""
    log_entries = []

    for plan in plans:
        source_dir = wiertsema_dir / plan["source"]
        target_dir = wiertsema_dir / plan["target"]

        if not source_dir.is_dir():
            log_entries.append({
                "action": "skip",
                "source": plan["source"],
                "reason": "source folder no longer exists",
            })
            continue

        if not target_dir.exists():
            source_dir.rename(target_dir)
            log_entries.append({
                "action": "rename",
                "source": plan["source"],
                "target": plan["target"],
                "file_count": plan["file_count"],
            })
        else:
            moved = 0
            for rel_path in plan["files"]:
                src_file = source_dir / rel_path
                dst_file = target_dir / rel_path

                if not src_file.exists():
                    continue

                dst_file.parent.mkdir(parents=True, exist_ok=True)

                if dst_file.exists():
                    src_mtime = src_file.stat().st_mtime
                    dst_mtime = dst_file.stat().st_mtime
                    if src_mtime > dst_mtime:
                        old_name = dst_file.stem + "_old" + dst_file.suffix
                        dst_file.rename(dst_file.with_name(old_name))
                        src_file.rename(dst_file)
                    else:
                        old_name = src_file.stem + "_old" + src_file.suffix
                        src_file.rename(dst_file.with_name(old_name))
                else:
                    src_file.rename(dst_file)
                moved += 1

            # Remove empty source directory tree
            _remove_empty_dirs(source_dir)

            log_entries.append({
                "action": "merge",
                "source": plan["source"],
                "target": plan["target"],
                "files_moved": moved,
                "conflicts": len(plan.get("conflicts", [])),
            })

    # Write log
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_data = {
        "timestamp": datetime.now().isoformat(),
        "entries": log_entries,
    }
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, default=str)

    return log_entries


def _remove_empty_dirs(path: Path) -> None:
    """Remove a directory tree if all directories are empty."""
    if not path.is_dir():
        return
    for child in path.iterdir():
        if child.is_dir():
            _remove_empty_dirs(child)
    if not any(path.iterdir()):
        path.rmdir()


def run_migration(
    wiertsema_dir: Path,
    apply: bool = False,
    validation_dir: Path | None = None,
) -> str:
    """Run the migration (dry-run or apply). Returns a report string."""
    lines = []

    # Migrate output_data
    plans, unresolvable = _collect_plans(wiertsema_dir)
    plans = _detect_conflicts(plans, wiertsema_dir)

    lines.append("=" * 70)
    lines.append("WIERTSEMA OUTPUT FOLDER MIGRATION")
    lines.append(f"Directory: {wiertsema_dir}")
    lines.append(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    lines.append("=" * 70)

    if not plans and not unresolvable:
        lines.append("\nNothing to migrate — all folders already use stable keys.")
        return "\n".join(lines)

    if plans:
        lines.append(f"\n{'Source':<55} {'Target':<15} {'Files':<8} {'Merge'}")
        lines.append("-" * 95)
        for plan in plans:
            merge_info = ", ".join(plan.get("merge_with", [])) or "-"
            lines.append(
                f"{plan['source']:<55} {plan['target']:<15} {plan['file_count']:<8} {merge_info}"
            )
            for conflict in plan.get("conflicts", []):
                newer = "src newer -> keep src" if conflict["src_newer"] else "dst newer -> keep dst"
                lines.append(f"  CONFLICT: {conflict['file']}  ({newer})")

    if unresolvable:
        lines.append(f"\nUnresolvable folders ({len(unresolvable)}):")
        for u in unresolvable:
            lines.append(f"  {u['source']}: {u['reason']}")

    if apply and plans:
        lines.append("\nApplying migration...")
        log_path = wiertsema_dir / "migration_log.json"
        log_entries = _apply_migration(plans, wiertsema_dir, log_path)

        # Also migrate validation_data if present
        if validation_dir and validation_dir.is_dir():
            val_plans, _ = _collect_plans(validation_dir)
            if val_plans:
                val_plans = _detect_conflicts(val_plans, validation_dir)
                val_log_path = validation_dir / "migration_log.json"
                val_entries = _apply_migration(val_plans, validation_dir, val_log_path)
                lines.append(f"Migrated {len(val_entries)} validation_data folder(s).")

        for entry in log_entries:
            action = entry["action"]
            if action == "rename":
                lines.append(f"  RENAMED: {entry['source']} -> {entry['target']} ({entry['file_count']} files)")
            elif action == "merge":
                lines.append(f"  MERGED:  {entry['source']} -> {entry['target']} ({entry['files_moved']} files, {entry['conflicts']} conflicts)")
            elif action == "skip":
                lines.append(f"  SKIPPED: {entry['source']} ({entry['reason']})")

        lines.append(f"\nMigration log written to: {log_path}")
    elif not apply:
        lines.append("\nThis is a dry run. Pass --apply to execute.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Migrate wiertsema output folders to stable-key naming")
    parser.add_argument("--apply", action="store_true", help="Execute the migration (default is dry-run)")
    parser.add_argument("--dir", type=Path, help="Override wiertsema output directory")
    args = parser.parse_args()

    repo_root = find_repo_root()
    wiertsema_dir = args.dir or (repo_root / "output_data" / "wiertsema")
    validation_dir = repo_root / "validation_data" / "wiertsema"

    report = run_migration(wiertsema_dir, apply=args.apply, validation_dir=validation_dir)
    print(report)


if __name__ == "__main__":
    main()
