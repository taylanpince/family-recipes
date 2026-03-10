#!/usr/bin/env python3
"""One-time migration: split a raw cookbook markdown into per-recipe pages.

Heuristics:
- A new recipe starts on a line beginning with '# ' (level-1 heading).
- Content continues until the next '# ' heading.

Outputs:
- Writes `docs/recipes/<slug>.md` for each recipe.
- Adds minimal frontmatter with slug+title; leaves the body as-is.

Intended workflow:
- Run once, then manually clean up recipes.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def slugify(title: str) -> str:
    s = title.strip().lower()
    s = s.replace("’", "'")
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: scripts/migrate_cookbook.py <path-to-raw-md>")
        return 2

    raw_path = Path(sys.argv[1])
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "docs" / "recipes"

    text = raw_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    # Find top-level headings
    heading_re = re.compile(r"^#\s+(.*)\s*$")
    sections: list[tuple[str, list[str]]] = []

    current_title: str | None = None
    current_body: list[str] = []

    for line in lines:
        m = heading_re.match(line)
        if m:
            # flush previous section (skip the cookbook title itself)
            if current_title and current_title.lower() != "cookbook":
                sections.append((current_title, current_body))
            current_title = m.group(1).strip()
            current_body = []
        else:
            # ignore any leading empty lines before first heading
            if current_title is None:
                continue
            current_body.append(line)

    if current_title and current_title.lower() != "cookbook":
        sections.append((current_title, current_body))

    if not sections:
        print("No recipe headings found.")
        return 1

    written = 0
    collisions: dict[str, int] = {}

    for title, body_lines in sections:
        slug = slugify(title)
        if slug in collisions:
            collisions[slug] += 1
            slug = f"{slug}-{collisions[slug]}"
        else:
            collisions[slug] = 1

        out_path = out_dir / f"{slug}.md"
        body = "\n".join(body_lines).strip() + "\n"

        content = (
            "---\n"
            f"slug: {slug}\n"
            f"title: {title.strip()}\n"
            "tags: []\n"
            "cuisine: \"\"\n"
            "difficulty: easy\n"
            "time_total_min: 0\n"
            "servings: 0\n"
            "ingredients: []\n"
            "---\n\n"
            f"{body}"
        )

        out_path.write_text(content, encoding="utf-8")
        written += 1

    print(f"Wrote {written} recipes to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
