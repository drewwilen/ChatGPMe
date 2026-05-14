from pathlib import Path
import re

SRC_DIR = Path("data/corpuses/shakespeare/text/works")
OUT_DIR = Path("data/corpuses/shakespeare/text/works_cleaned")

NOISE_EXACT = {
    "contents",
    "dramatis personae",
    "the end",
    "finis",
    "scene.",
}

NOISE_PREFIXES = (
    "scene ",
    "scene.",
    "act ",
    "act.",
    "enter ",
    "exit ",
    "exeunt",
    "flourish",
    "alarum",
    "sennet",
    "trumpets",
    "music",
)

RE_ROMAN = re.compile(r"^[IVXLCDM]+\.?$", re.IGNORECASE)
RE_DIGITS = re.compile(r"^\d+$")
RE_STAGE_BRACKETS = re.compile(r"\[[^\]]*\]")
RE_STAGE_PARENS = re.compile(r"\([^)]*(?:enter|exit|exeunt|aside|flourish|alarum|trumpets?|music|drum|march)[^)]*\)", re.IGNORECASE)
RE_SPEAKER = re.compile(r"^[A-Z][A-Z'\- ]{1,40}\.$")
RE_TITLEISH = re.compile(r"^(THE |A |ALL\b|LOVE\b|KING\b|MEASURE\b|MUCH\b|PERICLES\b|TROILUS\b|TWELFTH\b|VENUS\b|CYMBELINE\b)")
RE_UPPER_TITLE = re.compile(r"^[A-Z0-9 ,;:'’\-]+$")


def is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False

    low = s.lower()

    if low in NOISE_EXACT:
        return True

    if any(low.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True

    if RE_ROMAN.fullmatch(s):
        return True

    if RE_DIGITS.fullmatch(s):
        return True

    if RE_SPEAKER.fullmatch(s):
        return True

    # Remove file-level heading/title lines that are typically all caps in this corpus.
    if s.upper() == s and len(s) > 12 and RE_TITLEISH.match(s):
        return True

    return False


def clean_line(line: str) -> str:
    # Remove inline stage directions while preserving surrounding text.
    s = RE_STAGE_BRACKETS.sub("", line)
    s = RE_STAGE_PARENS.sub("", s)

    # Remove trailing line numbers from some poem tails, e.g. "... 1192"
    s = re.sub(r"\s+\d{1,5}\s*$", "", s)

    # Normalize whitespace without changing punctuation/wording.
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def clean_file(path: Path, out_path: Path) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out_lines: list[str] = []

    removed = 0
    in_dramatis = False
    seen_text = False

    for line in lines:
        stripped = line.strip()
        low = stripped.lower()

        # Drop cast list blocks entirely.
        if "dramatis person" in low:
            in_dramatis = True
            removed += 1
            continue

        if in_dramatis:
            # Keep skipping cast lines until we reach scene/act structure, then
            # let normal noise filters remove those headings as well.
            if low.startswith("scene") or low.startswith("act"):
                in_dramatis = False
            else:
                removed += 1
                continue

        if is_noise_line(line):
            removed += 1
            continue

        cleaned = clean_line(line)
        if not cleaned:
            # keep spacing only where useful; final compaction done below
            out_lines.append("")
        else:
            # Guard again after whitespace normalization.
            if RE_SPEAKER.fullmatch(cleaned):
                removed += 1
                continue

            # Drop opening all-caps work title line.
            if not seen_text and RE_UPPER_TITLE.fullmatch(cleaned) and " " in cleaned:
                removed += 1
                continue

            seen_text = True
            out_lines.append(cleaned)

    # Collapse blank runs to max 1 and trim outer blanks.
    compacted: list[str] = []
    prev_blank = False
    for line in out_lines:
        blank = line == ""
        if blank and prev_blank:
            continue
        compacted.append(line)
        prev_blank = blank

    while compacted and compacted[0] == "":
        compacted.pop(0)
    while compacted and compacted[-1] == "":
        compacted.pop()

    out_path.write_text("\n".join(compacted) + "\n", encoding="utf-8")
    return len(lines), removed


def main() -> None:
    if not SRC_DIR.exists():
        raise RuntimeError(f"Source directory not found: {SRC_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[str] = []
    total_files = 0

    for src in sorted(SRC_DIR.glob("*.txt")):
        if src.name.startswith("_"):
            continue

        dst = OUT_DIR / src.name
        before, removed = clean_file(src, dst)
        after = len(dst.read_text(encoding="utf-8").splitlines())

        total_files += 1
        manifest_rows.append(f"{src.name}\t{before}\t{after}\tremoved:{removed}")

    (OUT_DIR / "_cleaning_manifest.tsv").write_text("\n".join(manifest_rows) + "\n", encoding="utf-8")
    print(f"Cleaned {total_files} files into {OUT_DIR}")


if __name__ == "__main__":
    main()
