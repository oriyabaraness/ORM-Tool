#!/usr/bin/env python3
"""Organize ~/Downloads into a structured folder hierarchy."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

DOWNLOADS = Path.home() / "Downloads"
ROOT = DOWNLOADS / "_Organized"
MANIFEST = DOWNLOADS / "_organization_manifest.json"

STRUCTURE = {
    "Documents/Academic": [],
    "Documents/Financial & Legal": [],
    "Documents/Professional - Cyber & Security": [],
    "Documents/Professional - Other": [],
    "Documents/Personal & General": [],
    "Presentations": [],
    "Spreadsheets & Data/Spreadsheets": [],
    "Spreadsheets & Data/Datasets": [],
    "Media/Images": [],
    "Media/Video": [],
    "Media/Audio": [],
    "Archives": [],
    "Installers": [],
    "Email & Calendar": [],
    "Web & Code": [],
    "Fonts & Design": [],
    "Extracted Archives": [],
    "Misc": [],
}

SKIP_NAMES = {".localized", ".DS_Store", "_organization_manifest.json", "_Organized"}
SKIP_PREFIXES = (
    "Archives",
    "Installers",
    "Presentations",
    "Email & Calendar",
    "Web & Code",
    "Fonts & Design",
    "Extracted Archives",
    "Misc",
    "Documents",
    "Media",
    "Spreadsheets & Data",
)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".svg", ".bmp", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac"}
INSTALLER_EXT = {".dmg", ".pkg", ".exe", ".msi"}
ARCHIVE_EXT = {".zip", ".tar", ".gz", ".rar", ".7z"}
SPREADSHEET_EXT = {".xlsx", ".xls", ".numbers"}
DATA_EXT = {".csv", ".npy", ".json", ".parquet", ".tsv"}
PRESENTATION_EXT = {".pptx", ".ppt", ".key"}
DOC_EXT = {".pdf", ".docx", ".doc", ".txt", ".rtf", ".odt", ".epub"}
EMAIL_CAL_EXT = {".eml", ".emz", ".ics"}
WEB_CODE_EXT = {".html", ".htm", ".js", ".css", ".md", ".py", ".ipynb", ".vtt"}
FONT_DESIGN_EXT = {".ttf", ".otf", ".woff", ".woff2", ".ai", ".psd", ".sketch", ".fig"}
CITATION_EXT = {".enw", ".bib"}

ACADEMIC_PATTERNS = re.compile(
    r"ipis|inaf|baraness|assignment|university|carleton|presentation|thesis|"
    r"essay|group.*paper|course|take-?home|seminar|lecture|dissertation|"
    r"academic|student|professor|syllabus|bibliography|978-|10\.\d+/|s2\.0-|"
    r"midw|earth|ert[hH]|explosive|halifax|engineering",
    re.I,
)
FINANCIAL_PATTERNS = re.compile(
    r"lease|tax|slip|citibank|invoice|receipt|bank|mortgage|rental|payment|"
    r"t4|rrsp|paystub|payroll|statement|wire|transfer|notary|agreement|"
    r"employment|creditreport|סיטיבנק|מס|חשבונית",
    re.I,
)
CYBER_PATTERNS = re.compile(
    r"cyber|bcm|security|continuity|clearance|intelligence|intel|"
    r"surveillance|encryption|threat|vulnerability|nist|iso\s*27|emergency|"
    r"disaster|forensic|kill.?chain|smart.?grid",
    re.I,
)
PROFESSIONAL_PATTERNS = re.compile(
    r"resume|cv|cover.?letter|linkedin|job|interview|application|"
    r"gladstone|shopify|business|corporate|consulting|report|ihms",
    re.I,
)


def ensure_dirs() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    for rel in STRUCTURE:
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    parent = dest.parent
    n = 1
    while True:
        candidate = parent / f"{stem} ({n}){suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def categorize(name: str, suffix: str, is_dir: bool) -> str:
    if is_dir:
        return "Extracted Archives"

    if suffix in IMAGE_EXT:
        return "Media/Images"
    if suffix in VIDEO_EXT:
        return "Media/Video"
    if suffix in AUDIO_EXT:
        return "Media/Audio"
    if suffix in INSTALLER_EXT:
        return "Installers"
    if suffix in ARCHIVE_EXT:
        return "Archives"
    if suffix in PRESENTATION_EXT:
        if ACADEMIC_PATTERNS.search(name):
            return "Documents/Academic"
        return "Presentations"
    if suffix in SPREADSHEET_EXT:
        return "Spreadsheets & Data/Spreadsheets"
    if suffix in DATA_EXT:
        return "Spreadsheets & Data/Datasets"
    if suffix in EMAIL_CAL_EXT:
        return "Email & Calendar"
    if suffix in WEB_CODE_EXT:
        return "Web & Code"
    if suffix in FONT_DESIGN_EXT:
        return "Fonts & Design"
    if suffix in CITATION_EXT:
        return "Documents/Academic"

    if suffix in DOC_EXT or suffix == "":
        if ACADEMIC_PATTERNS.search(name):
            return "Documents/Academic"
        if FINANCIAL_PATTERNS.search(name):
            return "Documents/Financial & Legal"
        if CYBER_PATTERNS.search(name):
            return "Documents/Professional - Cyber & Security"
        if PROFESSIONAL_PATTERNS.search(name):
            return "Documents/Professional - Other"
        if suffix in DOC_EXT:
            return "Documents/Personal & General"
        return "Misc"

    return "Misc"


def should_skip(entry: Path) -> bool:
    name = entry.name
    if name in SKIP_NAMES or name.startswith("."):
        return True
    if entry == ROOT or ROOT in entry.parents:
        return True
    return name in SKIP_PREFIXES or name == "_Organized"


def move_item(src: Path, category: str) -> Path:
    dest_dir = ROOT / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_dest(dest_dir / src.name)
    shutil.move(str(src), str(dest))
    return dest


def consolidate_legacy() -> list[dict]:
    """Move items from the first partial run into _Organized."""
    moves: list[dict] = []
    legacy_roots = [
        DOWNLOADS / "Archives",
        DOWNLOADS / "Installers",
        DOWNLOADS / "Presentations",
        DOWNLOADS / "Email & Calendar",
        DOWNLOADS / "Web & Code",
        DOWNLOADS / "Fonts & Design",
        DOWNLOADS / "Extracted Archives",
        DOWNLOADS / "Misc",
        DOWNLOADS / "Documents",
        DOWNLOADS / "Media",
        DOWNLOADS / "Spreadsheets & Data",
    ]

    for legacy in legacy_roots:
        if not legacy.exists():
            continue
        if legacy == ROOT:
            continue

        if legacy.name == "Extracted Archives":
            # Preserve nested misplaced category trees
            nested_docs = legacy / "Documents"
            if nested_docs.exists():
                for sub in nested_docs.iterdir():
                    target_cat = f"Documents/{sub.name}"
                    if (ROOT / target_cat).parent.exists() or sub.is_dir():
                        for item in sub.rglob("*") if sub.is_dir() else [sub]:
                            if item.is_file():
                                rel_cat = target_cat if sub.is_dir() else "Documents/Personal & General"
                                dest = move_item(item, rel_cat)
                                moves.append({"from": str(item), "to": str(dest.relative_to(DOWNLOADS)), "note": "legacy nested"})
                shutil.rmtree(nested_docs, ignore_errors=True)

            nested_media = legacy / "Media"
            if nested_media.exists():
                for sub in nested_media.iterdir():
                    for item in (sub.rglob("*") if sub.is_dir() else [sub]):
                        if item.is_file():
                            dest = move_item(item, f"Media/{sub.name}")
                            moves.append({"from": str(item), "to": str(dest.relative_to(DOWNLOADS)), "note": "legacy nested"})
                shutil.rmtree(nested_media, ignore_errors=True)

        if legacy.name in STRUCTURE or legacy.name in {
            "Documents",
            "Media",
            "Spreadsheets & Data",
        }:
            for item in legacy.rglob("*"):
                if item.is_file():
                    rel = item.relative_to(legacy)
                    category = str(rel.parent) if rel.parent != Path(".") else legacy.name
                    if legacy.name == "Documents" and rel.parent != Path("."):
                        category = f"Documents/{rel.parent}"
                    elif legacy.name == "Media" and rel.parent != Path("."):
                        category = f"Media/{rel.parent}"
                    elif legacy.name == "Spreadsheets & Data" and rel.parent != Path("."):
                        category = f"Spreadsheets & Data/{rel.parent}"
                    elif legacy.name in STRUCTURE:
                        category = legacy.name
                    dest = move_item(item, category)
                    moves.append({"from": str(item), "to": str(dest.relative_to(DOWNLOADS)), "note": "legacy root"})
            shutil.rmtree(legacy, ignore_errors=True)
            continue

        # Flat legacy folders map 1:1 to categories
        category = legacy.name
        if legacy.is_dir():
            for item in list(legacy.iterdir()):
                if item.name in {"Documents", "Media"}:
                    continue
                if item.is_dir():
                    dest = unique_dest((ROOT / category) / item.name)
                    shutil.move(str(item), str(dest))
                    moves.append({"from": str(item), "to": str(dest.relative_to(DOWNLOADS)), "note": "legacy folder"})
                elif item.is_file():
                    dest = move_item(item, category)
                    moves.append({"from": str(item), "to": str(dest.relative_to(DOWNLOADS)), "note": "legacy file"})
            shutil.rmtree(legacy, ignore_errors=True)

    return moves


def organize() -> dict:
    ensure_dirs()
    moves: list[dict] = []
    skipped: list[str] = []
    errors: list[dict] = []

    moves.extend(consolidate_legacy())

    for entry in sorted(DOWNLOADS.iterdir(), key=lambda p: p.name.lower()):
        if should_skip(entry):
            skipped.append(entry.name)
            continue

        is_dir = entry.is_dir()
        suffix = entry.suffix.lower() if not is_dir else ""
        category = categorize(entry.name, suffix, is_dir)

        try:
            dest = move_item(entry, category)
            moves.append(
                {
                    "from": entry.name,
                    "to": str(dest.relative_to(DOWNLOADS)),
                    "category": category,
                    "type": "directory" if is_dir else "file",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": entry.name, "error": str(exc)})

    summary = {
        "timestamp": datetime.now().isoformat(),
        "downloads": str(DOWNLOADS),
        "organized_root": str(ROOT),
        "moved": len(moves),
        "skipped": len(skipped),
        "errors": len(errors),
        "by_category": {},
        "moves": moves,
        "skipped_items": skipped,
        "error_details": errors,
    }

    for m in moves:
        cat = m.get("category", m.get("to", "").split("/")[1:3])
        if isinstance(cat, list):
            cat = "/".join(cat) if cat else "unknown"
        if isinstance(cat, str) and cat.startswith("_Organized/"):
            cat = cat.removeprefix("_Organized/")
        summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1

    MANIFEST.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    summary = organize()
    print(f"Organized {summary['moved']} items")
    print(f"Root: {summary['organized_root']}")
    print(f"Skipped: {summary['skipped']} | Errors: {summary['errors']}")
    print("\nBy category:")
    for cat, count in sorted(summary["by_category"].items(), key=lambda x: (-x[1], str(x[0]))):
        print(f"  {cat}: {count}")
    remaining = [p.name for p in DOWNLOADS.iterdir() if not should_skip(p)]
    print(f"\nRemaining loose items at Downloads root: {len(remaining)}")
    print(f"Manifest: {MANIFEST}")


if __name__ == "__main__":
    main()
