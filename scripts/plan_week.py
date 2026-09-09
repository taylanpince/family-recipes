#!/usr/bin/env python3
"""Weekly menu builder - composes nightly menus of protein + carb + salad.

House rule: each dinner is 1 protein dish, 1 carb/starch dish, and usually a
salad next to it. The planner picks one recipe of each dish_type per night,
combining them in different permutations across the week while avoiding
anything cooked recently (reads log/cooked.csv).

Usage:
  scripts/plan_week.py                          # plan week of next Monday
  scripts/plan_week.py --days 5                 # weeknight-only plan
  scripts/plan_week.py --start 2026-09-07       # plan a specific week
  scripts/plan_week.py --seed 42                # reproducible plans
  scripts/plan_week.py --no-salad               # skip the nightly salad
  scripts/plan_week.py --carb-once              # never repeat a carb all week

Options:
  --days N            number of dinners to plan (default 7)
  --start DATE        week start date YYYY-MM-DD (default: next Monday)
  --seed N            random seed for reproducible plans
  --no-salad          omit the salad slot
  --carb-once         use each carb recipe at most once across the week
  --protein-once      use each protein recipe at most once across the week
  --max-time MIN      exclude recipes with time_total_min > MIN
  --exclude-tag TAG   exclude recipes with this tag (repeatable)
  --include-dish T    require dish_type T on >=1 pick (repeatable)
  --dish-types LIST   comma-separated slots, e.g. "protein,carb,salad,soup"
  --overwrite         replace an existing menu file for the same week
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "docs" / "recipes"
LOG_PATH = ROOT / "log" / "cooked.csv"
MENUS_DIR = ROOT / "docs" / "menus"
IGNORE_FILES = {"index.md", "conventions.md", "_template.md"}

DEFAULT_SLOTS = ["protein", "carb", "salad"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None
    fm = parts[1]
    recipe: dict = {"slug": path.stem}
    if m := re.search(r"^title:\s*(.+?)\s*$", fm, re.M):
        recipe["title"] = m.group(1).strip().strip('"')
    if m := re.search(r"^dish_type:\s*(\S+)", fm, re.M):
        recipe["dish_type"] = m.group(1).strip()
    if m := re.search(r"^cuisine:\s*(.+?)\s*$", fm, re.M):
        recipe["cuisine"] = m.group(1).strip().strip('"')
    if m := re.search(r"^time_total_min:\s*(\d+)", fm, re.M):
        recipe["time_total_min"] = int(m.group(1))
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
    out: dict[str, date] = {}
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


def recency_penalty(slug: str, recency: dict[str, date], today: date) -> float:
    """Big penalty for recently-cooked recipes so we rotate."""
    if last := recency.get(slug):
        days_since = (today - last).days
        if days_since <= 7:
            return 1000
        if days_since <= 21:
            return 100
        if days_since <= 45:
            return 10
    return 0


def build_slot_pools(
    recipes: list[dict],
    slots: list[str],
    max_time: int | None,
    exclude_tags: set[str],
    today: date,
) -> dict[str, list[dict]]:
    """For each slot, the eligible recipes ranked best-first (staples last-ish,
    long recipes later so weeknights stay quick)."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in recipes:
        dt = r.get("dish_type")
        if dt:
            by_type[dt].append(r)
    pools = {}
    for slot in slots:
        pool = by_type.get(slot, [])
        # skip unfilled recipes (missing time metadata) unless the slot has nothing else
        if filled := [r for r in pool if r.get("time_total_min", 0) > 0]:
            pool = filled
        if max_time is not None:
            pool = [r for r in pool if r.get("time_total_min", 0) <= max_time]
        if exclude_tags:
            pool = [r for r in pool if not exclude_tags & set(r["tags"])]
        # rank: recency penalty, then a light length penalty; stable
        pool = sorted(
            pool,
            key=lambda r: (
                recency_penalty(r["slug"], {}, today) if False else 0,
                r.get("time_total_min", 0) * 0.1,
                r["slug"],
            ),
        )
        pools[slot] = pool
    return pools


def compose_week(
    pools: dict[str, list[dict]],
    slots: list[str],
    days: int,
    recency: dict[str, date],
    once_rules: set[str],
    seed: int | None,
    today: date,
) -> list[list[dict]]:
    """Returns days x slots picks. Rotates through each slot's ranked pool;
    recipes used get pushed toward the back of the rotation so the week has
    different permutations. 'once' slots are removed after first use."""
    rng = random.Random(seed)
    rotation: dict[str, list[dict]] = {}
    for slot in slots:
        pool = pools.get(slot, [])[:]
        rng.shuffle(pool)
        # stable-ish: light sorting by (recency, time) after shuffle keeps variety
        pool.sort(key=lambda r: (recency_penalty(r["slug"], recency, today) + rng.random(),
                                 r.get("time_total_min", 0)))
        rotation[slot] = pool

    used: dict[str, set[str]] = defaultdict(set)
    week: list[list[dict]] = []
    for _ in range(days):
        night: list[dict] = []
        for slot in slots:
            pool = rotation.get(slot, [])
            pick = next((r for r in pool if r["slug"] not in used[slot]), None)
            if pick is None and pool:
                pick = pool[rng.randrange(len(pool))]  # exhausted; allow repeat
            if pick:
                night.append(pick)
                used[slot].add(pick["slug"])
                if slot in once_rules:
                    rotation[slot] = [r for r in rotation[slot] if r["slug"] != pick["slug"]]
                else:
                    # move used pick to the back so it won't repeat too soon
                    rotation[slot] = [r for r in rotation[slot] if r["slug"] != pick["slug"]] + [pick]
        week.append(night)
    return week


def fmt_minutes(m: int) -> str:
    if m >= 60 and m % 60 == 0:
        return f"{m // 60}h"
    if m >= 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m} min"


def collect_ingredients(picks: list[dict]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in picks:
        page = RECIPES_DIR / f"{r['slug']}.md"
        text = page.read_text(encoding="utf-8")
        parts = text.split("---\n", 2)
        fm = parts[1] if len(parts) >= 3 else ""
        if m := re.search(r"^ingredients:\s*$\n((?:\s+- .*\n)*)", fm, re.M):
            for line in m.group(1).splitlines():
                item = line.strip()[2:].strip()
                if item and item.lower() not in seen:
                    seen.add(item.lower())
                    out.append(item)
    return out


def render_menu_page(start: date, week: list[list[dict]], slots: list[str], plan_date: date) -> str:
    lines = [
        "---",
        f"slug: menu-{start.isoformat()}",
        f"title: Menu for week of {start.isoformat()}",
        "---",
        "",
        f"Plan generated {plan_date.isoformat()} by `scripts/plan_week.py`.",
        "",
    ]
    header = "| Day | " + " | ".join(s.capitalize() for s in slots) + " |"
    sep = "|-----" + "|--------" * len(slots) + "|"
    lines += [header, sep]
    all_picks: list[dict] = []
    for i, night in enumerate(week):
        day = DAY_NAMES[i % 7]
        cells = []
        for slot, r in zip(slots, night):
            if r is None:
                cells.append("-")
                continue
            all_picks.append(r)
            total = r.get("time_total_min", 0)
            cells.append(f"[{r['title']}](../recipes/{r['slug']}.md) ({fmt_minutes(total)})")
        lines.append(f"| {day} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## Grocery list (rough)",
        "",
        "Combined ingredients across the week - quantities not merged, check servings per recipe.",
        "",
    ]
    lines += [f"- {item}" for item in collect_ingredients(all_picks)]
    return "\n".join(lines) + "\n"


def render_index(menus_dir: Path) -> str:
    lines = ["# Weekly Menus", "", "Plans generated by `scripts/plan_week.py`. Newest first.", ""]
    for p in sorted(menus_dir.glob("menu-*.md"), reverse=True):
        text = p.read_text(encoding="utf-8")
        if m := re.search(r"^title:\s*(.+?)\s*$", text, re.M):
            lines.append(f"- [{m.group(1).strip().strip(chr(34))}]({p.name})")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start", default=None, help="YYYY-MM-DD, defaults to next Monday")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--slots", default=None, dest="dish_types",
                    help='comma-separated slots, e.g. "protein,carb,salad" (default)')
    ap.add_argument("--include-dish", action="append", default=[],
                    help="require this dish_type slot on at least one night (repeatable)")
    ap.add_argument("--no-salad", action="store_true", help="omit the salad slot")
    ap.add_argument("--carb-once", action="store_true", help="each carb recipe at most once")
    ap.add_argument("--protein-once", action="store_true", help="each protein recipe at most once")
    ap.add_argument("--max-time", type=int, default=None)
    ap.add_argument("--exclude-tag", action="append", default=[])
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    today = date.today()
    if args.start:
        start = datetime.strptime(args.start, "%Y-%m-%d").date()
    else:
        start = today + timedelta(days=(7 - today.weekday()) % 7 or 7)

    slots = (args.dish_types.split(",") if args.dish_types else DEFAULT_SLOTS)
    if args.no_salad:
        slots = [s for s in slots if s != "salad"]
    for extra in args.include_dish:
        if extra not in slots:
            slots.append(extra)
    once_rules = set()
    if args.carb_once and "carb" in slots:
        once_rules.add("carb")
    if args.protein_once and "protein" in slots:
        once_rules.add("protein")

    MENUS_DIR.mkdir(parents=True, exist_ok=True)
    menu_path = MENUS_DIR / f"menu-{start.isoformat()}.md"
    if menu_path.exists() and not args.overwrite:
        print(f"{menu_path} already exists; use --overwrite to replace it")
        return 1

    recipes = load_recipes()
    recency = load_recency()
    pools = build_slot_pools(recipes, slots, args.max_time, set(args.exclude_tag), today)
    missing = [s for s in slots if not pools.get(s)]
    if missing:
        print(f"Error: no eligible recipes for dish_type slot(s): {', '.join(missing)}")
        print("Available dish_types with recipes: "
              + ", ".join(sorted({r.get('dish_type', '') for r in recipes if r.get('dish_type')})))
        return 1

    week = compose_week(pools, slots, args.days, recency, once_rules, args.seed, today)
    menu_path.write_text(render_menu_page(start, week, slots, today), encoding="utf-8")
    (MENUS_DIR / "index.md").write_text(render_index(MENUS_DIR), encoding="utf-8")

    counts = Counter()
    for night in week:
        for r in night:
            counts[r.get("dish_type", "?")] += 1
    print(f"Wrote {menu_path} ({args.days} nights x {len(slots)} slots)")
    print(f"Slot fill counts: {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
