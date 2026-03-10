#!/usr/bin/env python3
"""Generate docs/recipes/index.md listing all recipe pages.

Keeps a small hand-written header, then auto-lists recipe links.
"""

from __future__ import annotations

import re
from pathlib import Path


def title_from_frontmatter(text: str) -> str | None:
    m = re.search(r"^title:\s*(.+?)\s*$", text, flags=re.M)
    if not m:
        return None
    t = m.group(1).strip().strip('"')
    return t or None


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    recipes_dir = root / "docs" / "recipes"
    index_path = recipes_dir / "index.md"

    files = sorted(p for p in recipes_dir.glob("*.md") if p.name not in {"index.md", "conventions.md", "_template.md"})

    items = []
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        title = title_from_frontmatter(text) or p.stem
        items.append((title, p.name))

    items.sort(key=lambda x: x[0].lower())

    header = """# Recipes

- [Conventions + schema](conventions.md)

## All recipes

"""

    body = "\n".join([f"- [{title}]({fname})" for title, fname in items]) + "\n"
    index_path.write_text(header + body, encoding="utf-8")

    print(f"Wrote {index_path} with {len(items)} recipes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
