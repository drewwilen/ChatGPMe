from pathlib import Path
import re
import unicodedata


SRC = Path("data/corpuses/shakespeare/text/complete_works_project_gutenberg.txt")
OUT_DIR = Path("data/corpuses/shakespeare/text/works")


def parse_titles(lines: list[str]) -> list[str]:
    titles: list[str] = []
    in_contents = False

    for line in lines:
        stripped = line.strip()

        if stripped == "Contents":
            in_contents = True
            continue

        if not in_contents:
            continue

        if line.startswith("    ") and stripped:
            titles.append(stripped)
            continue

        if titles and stripped == "":
            continue

        if titles and not line.startswith("    "):
            break

    return titles


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("’", "'")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def find_starts(lines: list[str], titles: list[str]) -> list[tuple[str, int]]:
    first = next((i for i, line in enumerate(lines) if line.strip() == titles[0]), None)
    if first is None:
        raise RuntimeError("Could not find first title occurrence")

    search_start = next((i for i in range(first + 1, len(lines)) if lines[i].strip() == titles[0]), None)
    if search_start is None:
        raise RuntimeError("Could not find first work start after contents")

    starts: list[tuple[str, int]] = []
    cursor = search_start

    for title in titles:
        line_num = next((i for i in range(cursor, len(lines)) if lines[i].strip() == title), None)
        if line_num is None:
            raise RuntimeError(f"Could not find heading for title: {title}")
        starts.append((title, line_num))
        cursor = line_num + 1

    return starts


def clean_chunk(lines: list[str]) -> list[str]:
    cleaned = [ln.rstrip() for ln in lines if not ln.startswith("*** END OF THE PROJECT GUTENBERG EBOOK")]

    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    out: list[str] = []
    blank_run = 0

    for ln in cleaned:
        if ln.strip() == "":
            blank_run += 1
            if blank_run <= 2:
                out.append("")
        else:
            blank_run = 0
            out.append(ln)

    return out


def main() -> None:
    if not SRC.exists():
        raise RuntimeError(f"Source corpus not found: {SRC}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines = SRC.read_text(encoding="utf-8").splitlines()
    titles = parse_titles(lines)

    if not titles:
        raise RuntimeError("Could not parse titles from contents")

    starts = find_starts(lines, titles)

    manifest_rows: list[str] = []

    for idx, (title, start) in enumerate(starts):
        end = starts[idx + 1][1] if idx + 1 < len(starts) else len(lines)
        chunk = clean_chunk(lines[start:end])

        out_name = f"{slugify(title)}.txt"
        out_path = OUT_DIR / out_name
        out_path.write_text("\n".join(chunk) + "\n", encoding="utf-8")

        manifest_rows.append(f"{out_name}\t{title}\t{len(chunk)} lines")

    (OUT_DIR / "_manifest.tsv").write_text("\n".join(manifest_rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(starts)} files to {OUT_DIR}")


if __name__ == "__main__":
    main()
