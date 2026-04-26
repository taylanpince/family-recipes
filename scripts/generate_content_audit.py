#!/usr/bin/env python3
"""Generate a content audit / punch list for recipe completion.

This reports only gaps already present in the source. It does not infer or invent
missing content.
"""

from __future__ import annotations

import re
from pathlib import Path

IGNORE = {"index.md", "conventions.md", "_template.md"}


def split_frontmatter(text: str) -> tuple[str, str] | None:
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    _, fm, body = parts
    return fm, body


def scalar(fm: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return None
    value = m.group(1).strip().strip('"')
    return value or None


def listv(fm: str, key: str) -> list[str]:
    m = re.search(rf"^{re.escape(key)}:\s*\n((?:\s+- .*\n?)*)", fm, re.M)
    if not m:
        return []
    return [ln.strip()[1:].strip() for ln in m.group(1).splitlines() if ln.strip().startswith("-")]


def visible_body(body: str) -> str:
    body = re.sub(
        r"\n?<!-- GENERATED_RECIPE_METADATA_START -->.*?<!-- GENERATED_RECIPE_METADATA_END -->\n?",
        "\n",
        body,
        flags=re.S,
    )
    return body.strip()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    recipes_dir = root / "docs" / "recipes"
    out_path = root / "docs" / "content-audit.md"

    recipes = []
    for path in sorted(recipes_dir.glob("*.md")):
        if path.name in IGNORE:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        parsed = split_frontmatter(text)
        if not parsed:
            continue
        fm, body = parsed
        title = scalar(fm, "title") or path.stem
        cuisine = scalar(fm, "cuisine")
        difficulty = scalar(fm, "difficulty")
        time_total = scalar(fm, "time_total_min")
        servings = scalar(fm, "servings")
        ingredients = listv(fm, "ingredients")
        tags = listv(fm, "tags")

        clean_body = visible_body(body)
        steps = [ln for ln in clean_body.splitlines() if re.match(r"^\s*\d+\.\s+", ln)]
        placeholder_markers = [
            marker
            for marker in [
                "placeholder",
                "todo",
                "details can be filled in later",
                "method not specified",
                "source note",
            ]
            if marker.lower() in clean_body.lower()
        ]
        vague_ingredients = [
            item for item in ingredients if len(item.split()) <= 2 and not re.search(r"\d", item)
        ]

        issues: list[str] = []
        if not cuisine:
            issues.append("Missing cuisine metadata")
        if not difficulty:
            issues.append("Missing difficulty metadata")
        if not time_total or time_total == "0":
            issues.append("Missing usable total time")
        if not servings or servings == "0":
            issues.append("Missing usable servings")
        if len(ingredients) < 3:
            issues.append(f"Very short ingredients list ({len(ingredients)} item{'s' if len(ingredients) != 1 else ''})")
        if ingredients and len(vague_ingredients) == len(ingredients):
            issues.append("Ingredients list is entirely vague shorthand")
        if len(steps) == 0:
            issues.append("No steps in body")
        elif len(steps) < 3:
            issues.append(f"Very short steps section ({len(steps)} step{'s' if len(steps) != 1 else ''})")
        if placeholder_markers:
            issues.append("Contains placeholder / incomplete-source wording")

        severity = "ok"
        if any(
            issue in issues
            for issue in [
                "No steps in body",
                "Contains placeholder / incomplete-source wording",
            ]
        ):
            severity = "critical"
        elif issues:
            severity = "needs-attention"

        recipes.append(
            {
                "file": path.name,
                "title": title,
                "severity": severity,
                "issues": issues,
                "ingredients": ingredients,
                "vague_ingredients": vague_ingredients,
                "steps_count": len(steps),
                "tags": tags,
            }
        )

    critical = [r for r in recipes if r["severity"] == "critical"]
    attention = [r for r in recipes if r["severity"] == "needs-attention"]
    ok = [r for r in recipes if r["severity"] == "ok"]

    lines: list[str] = [
        "# Recipe Content Audit",
        "",
        "This is a punch list of content gaps already present in the recipe files.",
        "No missing recipe details have been inferred or invented.",
        "",
        "## Summary",
        "",
        f"- Total recipes audited: **{len(recipes)}**",
        f"- Critical follow-up needed: **{len(critical)}**",
        f"- Needs attention: **{len(attention)}**",
        f"- Looks structurally okay: **{len(ok)}**",
        "",
        "## Critical follow-up",
        "",
    ]

    if critical:
        for r in critical:
            lines.append(f"- [{r['title']}](recipes/{r['file']}) (`{r['file']}`)")
    else:
        lines.append("- None")

    lines.extend(["", "## Recipe-by-recipe punch list", ""])

    severity_rank = {"critical": 0, "needs-attention": 1, "ok": 2}
    for r in sorted(recipes, key=lambda x: (severity_rank[x["severity"]], x["title"].lower())):
        lines.append(f"### {r['title']}")
        lines.append("")
        lines.append(f"- File: `docs/recipes/{r['file']}`")
        lines.append(f"- Status: **{r['severity']}**")
        if r["issues"]:
            lines.append("- Issues:")
            for issue in r["issues"]:
                lines.append(f"  - {issue}")
        else:
            lines.append("- Issues: none flagged")
        if r["vague_ingredients"]:
            lines.append("- Vague ingredient entries to review:")
            for item in r["vague_ingredients"]:
                lines.append(f"  - {item}")
        lines.append("")

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
