#!/usr/bin/env python3
"""Render visible recipe metadata from frontmatter into recipe pages.

This keeps ingredients and basic metadata visible on the published MkDocs page
without inventing new content. The block is idempotent and can be re-rendered
safely whenever frontmatter changes.
"""

from __future__ import annotations

import re
from pathlib import Path

IGNORE = {"index.md", "conventions.md", "_template.md"}
START = "<!-- GENERATED_RECIPE_METADATA_START -->"
END = "<!-- GENERATED_RECIPE_METADATA_END -->"


def split_frontmatter(text: str) -> tuple[str, str] | None:
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    _, fm, body = parts
    return fm, body.lstrip("\n")


def parse_scalar(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return None
    value = m.group(1).strip().strip('"')
    return value or None


def parse_list(fm: str, key: str) -> list[str]:
    m = re.search(rf"^{re.escape(key)}:\s*\n((?:\s+- .*\n?)*)", fm, re.M)
    if not m:
        return []
    items = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("-"):
            items.append(stripped[1:].strip())
    return items


def strip_generated_block(body: str) -> str:
    pattern = re.compile(
        rf"\n?{re.escape(START)}.*?{re.escape(END)}\n?", re.S
    )
    return pattern.sub("", body).lstrip("\n")


def split_photo_block(body: str) -> tuple[str, str]:
    pattern = re.compile(
        rf"({re.escape('<!-- RECIPE_PHOTO_START -->')}.*?{re.escape('<!-- RECIPE_PHOTO_END -->')}\n*)",
        re.S,
    )
    m = pattern.search(body)
    if not m:
        return "", body.lstrip("\n")
    photo = m.group(1).strip() + "\n\n"
    rest = (body[:m.start()] + body[m.end():]).lstrip("\n")
    return photo, rest


def build_block(fm: str) -> str:
    cuisine = parse_scalar(fm, "cuisine")
    difficulty = parse_scalar(fm, "difficulty")
    time_total_min = parse_scalar(fm, "time_total_min")
    servings = parse_scalar(fm, "servings")
    tags = parse_list(fm, "tags")
    ingredients = parse_list(fm, "ingredients")

    lines: list[str] = [START, "## Recipe details", ""]

    if cuisine:
        lines.append(f"- **Cuisine:** {cuisine}")
    if difficulty:
        lines.append(f"- **Difficulty:** {difficulty}")
    if time_total_min and time_total_min != "0":
        lines.append(f"- **Total time:** {time_total_min} min")
    if servings and servings != "0":
        lines.append(f"- **Servings:** {servings}")
    if tags:
        lines.append(f"- **Tags:** {', '.join(tags)}")

    if lines[-1] != "":
        lines.append("")

    if ingredients:
        lines.extend(["## Ingredients", ""])
        lines.extend([f"- {item}" for item in ingredients])
        lines.append("")

    lines.append(END)
    return "\n".join(lines).rstrip() + "\n\n"


def render_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="ignore")
    parsed = split_frontmatter(text)
    if not parsed:
        return False
    fm, body = parsed
    cleaned = strip_generated_block(body)
    photo_block, remainder = split_photo_block(cleaned)
    block = build_block(fm)
    new_text = f"---\n{fm}---\n\n{photo_block}{block}{remainder.lstrip()}"
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    recipes_dir = root / "docs" / "recipes"
    changed = 0
    for path in sorted(recipes_dir.glob("*.md")):
        if path.name in IGNORE:
            continue
        if render_file(path):
            changed += 1
    print(f"Rendered visible metadata for {changed} recipe files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
