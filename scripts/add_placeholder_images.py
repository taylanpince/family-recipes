#!/usr/bin/env python3
"""Generate nice placeholder images (SVG) for each recipe and inject into markdown.

- Writes SVGs to: docs/assets/recipes/<slug>.svg
- Adds a hero image line after frontmatter if missing:
    ![<title>](../assets/recipes/<slug>.svg)

Safe to rerun; it won't duplicate the image line.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


IGNORE = {"index.md", "conventions.md", "_template.md"}


def hex_color_from_slug(slug: str) -> str:
    h = hashlib.sha256(slug.encode("utf-8")).hexdigest()
    # pick a pleasant-ish mid-range color
    r = int(h[0:2], 16) // 2 + 64
    g = int(h[2:4], 16) // 2 + 64
    b = int(h[4:6], 16) // 2 + 64
    return f"#{r:02x}{g:02x}{b:02x}"


def emoji_for_tags(tags: list[str]) -> str:
    t = {x.strip().lower() for x in tags}
    if "soup" in t or "stock" in t:
        return "🥣"
    if "salad" in t:
        return "🥗"
    if "breakfast" in t or "pancakes" in t:
        return "🥞"
    if "fish" in t:
        return "🐟"
    if "chicken" in t:
        return "🍗"
    if "dumplings" in t:
        return "🥟"
    if "meatballs" in t:
        return "🧆"
    if "vegetarian" in t:
        return "🥕"
    if "stew" in t:
        return "🍲"
    if "turkish" in t:
        return "🧿"
    return "🍽️"


def parse_frontmatter(md: str) -> tuple[dict[str, object], str, str] | None:
    if not md.startswith("---"):
        return None
    parts = md.split("---", 2)
    if len(parts) < 3:
        return None
    fm_text = parts[1].strip("\n")
    rest = parts[2].lstrip("\n")

    data: dict[str, object] = {}

    # super-light YAML parsing (only for our simple keys)
    current_key = None
    for line in fm_text.splitlines():
        if not line.strip():
            continue
        if re.match(r"^[A-Za-z0-9_]+:\s*", line):
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            current_key = key
            if val == "[]":
                data[key] = []
            elif val.startswith('"') and val.endswith('"'):
                data[key] = val.strip('"')
            else:
                data[key] = val
        elif current_key == "tags" and line.strip().startswith("-"):
            data.setdefault("tags", [])
            if isinstance(data["tags"], list):
                data["tags"].append(line.strip().lstrip("-").strip())

    return data, ("---\n" + fm_text + "\n---\n"), rest


def make_svg(title: str, slug: str, emoji: str) -> str:
    bg = hex_color_from_slug(slug)
    # simple gradient
    bg2 = hex_color_from_slug(slug + "x")
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    return f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1200\" height=\"630\" viewBox=\"0 0 1200 630\" role=\"img\" aria-label=\"{safe_title}\">
  <defs>
    <linearGradient id=\"g\" x1=\"0\" x2=\"1\" y1=\"0\" y2=\"1\">
      <stop offset=\"0%\" stop-color=\"{bg}\"/>
      <stop offset=\"100%\" stop-color=\"{bg2}\"/>
    </linearGradient>
    <filter id=\"shadow\" x=\"-20%\" y=\"-20%\" width=\"140%\" height=\"140%\">
      <feDropShadow dx=\"0\" dy=\"10\" stdDeviation=\"18\" flood-color=\"#000\" flood-opacity=\"0.25\"/>
    </filter>
  </defs>

  <rect width=\"1200\" height=\"630\" fill=\"url(#g)\"/>

  <g filter=\"url(#shadow)\">
    <rect x=\"70\" y=\"110\" width=\"1060\" height=\"410\" rx=\"28\" fill=\"rgba(255,255,255,0.14)\" stroke=\"rgba(255,255,255,0.25)\"/>
  </g>

  <text x=\"120\" y=\"235\" font-size=\"88\" font-family=\"ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial\" fill=\"rgba(255,255,255,0.95)\">{emoji}</text>

  <text x=\"120\" y=\"345\" font-size=\"64\" font-weight=\"700\" font-family=\"ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial\" fill=\"white\">{safe_title}</text>

  <text x=\"120\" y=\"420\" font-size=\"28\" font-family=\"ui-sans-serif, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial\" fill=\"rgba(255,255,255,0.85)\">kaizenmusings.com/family-recipes</text>
</svg>
"""


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    recipes_dir = root / "docs" / "recipes"
    assets_dir = root / "docs" / "assets" / "recipes"
    assets_dir.mkdir(parents=True, exist_ok=True)

    changed_md = 0
    written_svg = 0

    for path in sorted(recipes_dir.glob("*.md")):
        if path.name in IGNORE:
            continue

        md = path.read_text(encoding="utf-8", errors="ignore")
        parsed = parse_frontmatter(md)
        if not parsed:
            continue
        data, fm_wrapper, rest = parsed

        slug = str(data.get("slug") or path.stem).strip()
        title = str(data.get("title") or path.stem).strip().strip('"')
        tags = data.get("tags")
        if not isinstance(tags, list):
            tags = []

        emoji = emoji_for_tags(tags)

        svg_path = assets_dir / f"{slug}.svg"
        svg = make_svg(title=title, slug=slug, emoji=emoji)
        svg_path.write_text(svg, encoding="utf-8")
        written_svg += 1

        hero_line = f"![{title}](../assets/recipes/{slug}.svg)"

        if hero_line not in md:
            # Insert right after frontmatter wrapper
            new_md = fm_wrapper + "\n" + hero_line + "\n\n" + rest.lstrip("\n")
            path.write_text(new_md, encoding="utf-8")
            changed_md += 1

    print(f"Wrote {written_svg} SVG placeholders; updated {changed_md} recipe markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
