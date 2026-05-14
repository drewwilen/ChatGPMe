from pathlib import Path
import re

IN_DIR = Path("data/corpuses/trump/text")
OUT_DIR = Path("data/corpuses/trump/text_cleaned")

# Patterns to remove entirely (lines that are metadata, not speech)
SKIP_PATTERNS = [
    r"^Q\.\s+",  # Reporter question prefix
    r"^Q&A:",  # Q&A header
    r"^\[.*\]$",  # Bracketed stage directions
    r"^The President\.\s*$",  # Bare speaker label
    r"^Pool Report",  # Pool report markers
    r"^Title:",  # Metadata lines
    r"^Date:",
    r"^Source:",
    r"^---+$",  # Separator lines
    r"^\s*\*\*\*",  # Asterisk separators
]

# Common reporter/non-Trump speaker prefixes to remove (for lines that start with them)
NON_TRUMP_SPEAKERS = [
    r"^Q\.",
    r"^Reporter\s+",
    r"^Amb\.\s+",
    r"^Ms\.\s+",
    r"^Mr\.\s+",
    r"^Dr\.\s+",
    r"^Secretary\s+",
    r"^Admiral\s+",
    r"^General\s+",
    r"^Prime Minister\s+",
    r"^President\s+(?!Trump)",
    r"^Vice President\s+",
    r"^First Lady\s+",
    r"^Speaker\s+(?!Trump)",
    r"^Moderator\s+",
    r"^Governor\s+",
    r"^Senator\s+",
    r"^Representative\s+",
    r"^Mayor\s+",
    r"^Archbishop\s+",
    r"^Reverend\s+",
    r"^Judge\s+",
    r"^Ambassador\s+",
    r"^Correspondent\s+",
    r"^Anchor\s+",
    r"^Host\s+",
]

# Compile patterns
skip_patterns_compiled = [re.compile(p, re.IGNORECASE) for p in SKIP_PATTERNS]
non_trump_compiled = [re.compile(p, re.IGNORECASE) for p in NON_TRUMP_SPEAKERS]

# Patterns that indicate Trump is speaking
TRUMP_MARKERS = [
    r"(?:^|\n)\s*(?:The )?President(?:\s+Trump)?\.\s+",  # Speaker label
    r"(?:^|\n)\s*Trump\.\s+",
    r"(?:^|\n)\s*Mr\.\s+Trump\.\s+",
]


def clean_line_content(line: str) -> str:
    """Remove speaker labels and clean up the line content."""
    stripped = line.strip()
    
    # Remove leading speaker labels like "The President.", "The President. ", etc.
    cleaned = re.sub(
        r"^(?:The\s+)?(?:President|Mr\.\s+Trump)(?:\s+Trump)?\.?\s+",
        "",
        stripped,
        flags=re.IGNORECASE,
    ).strip()
    
    return cleaned



def is_non_trump_line(line: str) -> bool:
    """Check if line starts with a non-Trump speaker label."""
    for pattern in non_trump_compiled:
        if pattern.match(line.strip()):
            return True
    return False


def clean_text(text: str) -> str:
    """Clean a Trump document to keep only Trump's speech."""
    lines = text.splitlines()
    clean_lines: list[str] = []

    skip_until_blank = False

    for line in lines:
        # Skip lines that match our skip patterns entirely
        stripped = line.strip()
        
        if not stripped:
            # Keep blank lines for paragraph spacing
            if clean_lines and clean_lines[-1] != "":
                clean_lines.append("")
            continue
        
        # Check skip patterns
        skip = False
        for pattern in skip_patterns_compiled:
            if pattern.search(line):
                skip = True
                break
        if skip:
            continue

        # If we encounter a non-Trump speaker, skip this line
        if is_non_trump_line(stripped):
            skip_until_blank = True
            continue

        if skip_until_blank:
            if not stripped or "president" in stripped.lower() or "trump" in stripped.lower():
                skip_until_blank = False
                if "president" in stripped.lower() or "trump" in stripped.lower():
                    continue
            else:
                continue

        # Clean speaker labels from the line content
        cleaned = clean_line_content(stripped)

        # Skip if nothing left after removing speaker label
        if not cleaned:
            continue

        # Keep this line
        clean_lines.append(cleaned)

    # Collapse excessive blank lines to max 2
    final_lines: list[str] = []
    blank_count = 0
    for line in clean_lines:
        if line == "":
            blank_count += 1
            if blank_count <= 2:
                final_lines.append(line)
        else:
            blank_count = 0
            final_lines.append(line)

    # Trim outer blanks
    while final_lines and final_lines[0] == "":
        final_lines.pop(0)
    while final_lines and final_lines[-1] == "":
        final_lines.pop()

    return "\n".join(final_lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[str] = []
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}

    for src in sorted(IN_DIR.glob("*.txt")):
        if src.name.startswith("_"):
            continue

        text = src.read_text(encoding="utf-8")
        before_counts[src.name] = len(text)

        cleaned = clean_text(text)
        after_counts[src.name] = len(cleaned)

        dst = OUT_DIR / src.name
        dst.write_text(cleaned + "\n", encoding="utf-8")

        manifest_rows.append(
            f"{src.name}\t{before_counts[src.name]}\t{after_counts[src.name]}"
        )

    (OUT_DIR / "_cleaning_manifest.tsv").write_text(
        "filename\tbefore_chars\tafter_chars\n" + "\n".join(manifest_rows) + "\n",
        encoding="utf-8",
    )

    total_before = sum(before_counts.values())
    total_after = sum(after_counts.values())
    reduction_pct = 100 * (total_before - total_after) / total_before if total_before else 0

    print(f"Cleaned {len(manifest_rows)} Trump speech files")
    print(f"Total before: {total_before:,} chars")
    print(f"Total after: {total_after:,} chars")
    print(f"Reduction: {reduction_pct:.1f}%")
    print(f"Output: {OUT_DIR}")


if __name__ == "__main__":
    main()
