#!/usr/bin/env python3
"""Weekly menu builder.

Picks dinners for a week from recipe frontmatter, avoiding recently-cooked
recipes (reads log/cooked.csv), and writes a Markdown plan page under
docs/menus/.

Usage:
  scripts/plan_week.py                          # plan week of next Monday
  scripts/plan_week.py --days 5 --max-time 60   # only weeknight-friendly picks
  scripts/plan_week.py --start 2026-09-07       # plan a specific week
  scripts/plan_week.py --seed 42                # reproducible shuffle

Options:
  --days N            number of dinners to plan (default 7)
  --start DATE        Monday (any day works, week starts here) YYYY-MM-DD
  --max-time MIN      exclude recipes with time_total_min > MIN
  --exclude-tag TAG   exclude recipes with this tag (repeatable)
  --include-tag TAG   require this tag on at least one pick (repeatable)
  --seed N            random seed for reproducible plans
  --overwrite         replace an existing menu file for the same week
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "docs" / "recipes"
LOG_PATH = ROOT / "log" / "cooked.csv"
MENUS_DIR = ROOT / "docs" / "menus"
IGNORE_FILES = {"index.md", "conventions.md", "_template.md"}
DEFAULT_EXCLUDE_TAGS = ["breakfast", "pickles", "sides", "side", "stock", "pastry"]

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    fm = parts[1]
    recipe = {"slug": path.stem}
    if m := re.search(r"^title:\s*(.+?)\s*$", fm, re.M):
        recipe["title"] = m.group(1).strip().strip('"')
    if m := re.search(r"^cuisine:\s*(.+?)\s*$", fm, re.M):
        recipe["cuisine"] = m.group(1).strip().strip('"')
    if m := re.search(r"^time_total_min:\s*(\d+)", fm, re.M):
        recipe["time_total_min"] = int(m.group(1))
    if m := re.search(r"^servings:\s*(\d+)", fm, re.M):
        recipe["servings"] = int(m.group(1))
    tags = []
    if m := re.search(r"^tags:\s*$\n((?:\s+- .*\n)*)", fm, re.M):
        tags = [line.strip()[2:].strip() for line in m.group(1).splitlines() if line.strip().startswith("-")]
    elif m := re.search(r"^tags:\s*\[(.*?)\]", fm, re.M):
        tags = [t.strip().strip('"') for t in m.group(1).split(",") if t.strip()]
    recipe["tags"] = tags
    return recipe


def load_recipes() -> list[dict]:
    recipes = []
    for path in sorted(RECIPES_DIR.glob("*.md")):
        if path.name in IGNORE_FILES:
            continue
        if r := parse_frontmatter(path):
            recipes.append(r)
    return recipes


def load_recency() -> dict[str, date]:
    """slug -> most recent cooked date."""
    if not LOG_PATH.exists():
        return {}
    out = {}
    with LOG_PATH.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = (row.get("recipe_slug") or "").strip()
            d = (row.get("date") or "").strip()
            if not slug or not d:
                continue
            try:
                parsed = datetime.strptime(d, "%Y-%m-%d").date()
            except ValueError:
                continue
            if slug not in out or parsed > out[slug]:
                out[slug] = parsed
    return out


def score(recipe: dict, recency: dict[str, date], today: date) -> float:
    """Lower is better. Recently-cooked recipes get a big penalty;
    long recipes get a mild penalty so weeknights stay quick."""
    s = 0.0
    if last := recency.get(recipe["slug"]):
        days_since = (today - last).days
        if days_since <= 7:
            s += 1000
        elif days_since <= 21:
            s += 100
        elif days_since <= 45:
            s += 10
    s += recipe.get("time_total_min", 0) * 0.1
    return s


def pick_menu(
    recipes: list[dict],
    recency: dict[str, date],
    days: int,
    max_time: int | None,
    exclude_tags: set[str],
    include_tags: set[str],
    seed: int | None,
    today: date,
    allow_unfilled: bool = False,
) -> list[dict]:
    pool = recipes[:]
    if not allow_unfilled:
        pool = [r for r in pool if r.get("time_total_min", 0) > 0]
    if max_time is not None:
        pool = [r for r in pool if r.get("time_total_min", 0) <= max_time]
    if exclude_tags:
        pool = [r for r in pool if not exclude_tags & set(r["tags"])]
    if include_tags:
        must_have = [r for r in pool if include_tags & set(r["tags"])]
        if must_have:
            # guarantee at least one include-tagged pick, rest from full pool
            rng = random.Random(seed)
            anchor = rng.choice(must_have)
            rest_pool = [r for r in pool if r["slug"] != anchor["slug"]]
            rng.shuffle(rest_pool)
            rest = sorted(rest_pool, key=lambda r: score(r, recency, today) + rng.random())
            return [anchor] + rest[: days - 1]
    rng = random.Random(seed)
    rng.shuffle(pool)
    return sorted(pool, key=lambda r: score(r, recency, today) + rng.random())[:days]


def fmt_minutes(m: int) -> str:
    if m >= 60 and m % 60 == 0:
        return f"{m // 60}h"
    if m >= 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m} min"


def render_menu_page(start: date, picks: list[dict], plan_date: date) -> str:
    lines = [
        f"---",
        f"slug: menu-{start.isoformat()}",
        f"title: Menu for week of {start.isoformat()}",
        f"---",
        "",
        f"Plan generated {plan_date.isoformat()} by `scripts/plan_week.py`.",
        "",
        "| Day | Recipe | Time | Tags |",
        "|-----|--------|------|------|",
    ]
    for i, r in enumerate(picks):
        day = DAY_NAMES[i % 7]
        tags = ", ".join(r["tags"][:4]) if r["tags"] else ""
        lines.append(
            f"| {day} | [{r['title']}](../recipes/{r['slug']}.md) "
            f"| {fmt_minutes(r.get('time_total_min', 0))} | {tags} |"
        )
    lines += [
        "",
        "## Grocery list (rough)",
        "",
        "Combined ingredients from all planned recipes - quantities not merged, check servings per recipe.",
        "",
    ]
    seen = set()
    for r in picks:
        page = RECIPES_DIR / f"{r['slug']}.md"
        text = page.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        fm = parts[1] if len(parts) >= 3 else ""
        if m := re.search(r"^ingredients:\s*$\n((?:\s+- .*\n)*)", fm, re.M):
            items = [line.strip()[2:].strip() for line in m.group(1).splitlines()]
            for item in items:
                if item.lower() not in seen:
                    seen.add(item.lower())
                    lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def render_index(menus_dir: Path) -> str:
    lines = ["# Weekly Menus", "", "Plans generated by `scripts/plan_week.py`. Newest first.", ""]
    pages = sorted(menus_dir.glob("menu-*.md"), reverse=True)
    for p in pages:
        text = p.read_text(encoding="utf-8")
        if m := re.search(r"^title:\s*(.+?)\s*$", text, re.M):
            lines.append(f"- [{m.group(1).strip().strip(chr(34))}]({p.name})")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to next Monday")
    ap.add_argument("--max-time", type=int, default=None)
    ap.add_argument("--exclude-tag", action="append", default=[],
                    help="exclude recipes with this tag (repeatable); defaults to "
                         f"{DEFAULT_EXCLUDE_TAGS} unless --no-default-exclude")
    ap.add_argument("--no-default-exclude", action="store_true")
    ap.add_argument("--include-tag", action="append", default=[])
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--allow-unfilled", action="store_true",
                    help="include recipes missing time metadata (the unfilled criticals)")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    if args.no_default_exclude:
        exclude_tags = list(args.exclude_tag)
    else:
        exclude_tags = list(dict.fromkeys(DEFAULT_EXCLUDE_TAGS + list(args.exclude_tag)))

    today = date.today()
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    MENUS_DIR.mkdir(parents=True, exist_ok=True)
    menu_path = MENUS_DIR / f"menu-{start.isoformat()}.md"
    if menu_path.exists() and not args.overwrite:
        print(f"{menu_path} already exists; use --overwrite to replace it")
        return 1

    recipes = load_recipes()
    recency = load_recency()
    picks = pick_menu(
        recipes,
        recency,
        args.days,
        args.max_time,
        set(exclude_tags),
        set(args.include_tag),
        args.seed,
        today,
        allow_unfilled=args.allow_unfilled,
    )
    if len(picks) < args.days:
        print(f"Warning: only {len(picks)} recipes matched constraints (wanted {args.days})")

    menu_path.write_text(render_menu_page(start, picks, today), encoding="utf-8")
    (MENUS_DIR / "index.md").write_text(render_index(MENUS_DIR), encoding="utf-8")
    print(f"Wrote {menu_path} ({len(picks)} dinners)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
