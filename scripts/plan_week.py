#!/usr/bin/env python3
"""Weekly menu builder - composes nightly menus of protein + carb + salad.

House rule: each dinner is 1 protein dish, 1 carb/starch dish, and usually a
salad next to it. The planner picks one recipe of each dish_type per night,
combining them in different permutations across the week while avoiding
anything cooked recently (reads log/cooked.csv).

Weekly themes (planner-config.json) pin certain nights: e.g. Fish Tuesday,
Friday cookout, one vegetarian dinner per week.

Usage:
  scripts/plan_week.py                          # plan week of next Monday
  scripts/plan_week.py --days 5                 # weeknight-only plan
  scripts/plan_week.py --start 2026-09-07       # plan a specific week
  scripts/plan_week.py --seed 42                # reproducible plans
  scripts/plan_week.py --no-salad               # skip the nightly salad
  scripts/plan_week.py --no-themes              # ignore configured themes
  scripts/plan_week.py --carb-once              # never repeat a carb all week

Options:
  --days N            number of dinners to plan (default 7)
  --start DATE        week start date YYYY-MM-DD (default: next Monday)
  --seed N            random seed for reproducible plans
  --no-salad          omit the salad slot
  --no-themes         ignore planner-config.json themes
  --carb-once         use each carb recipe at most once across the week
  --protein-once      use each protein recipe at most once across the week
  --max-time MIN      exclude recipes with time_total_min > MIN
  --exclude-tag TAG   exclude recipes with this tag (repeatable)
  --dish-types LIST   comma-separated slots, e.g. "protein,carb,salad,soup"
  --overwrite         replace an existing menu file for the same week
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPES_DIR = ROOT / "docs" / "recipes"
LOG_PATH = ROOT / "log" / "cooked.csv"
MENUS_DIR = ROOT / "docs" / "menus"
CONFIG_PATH = ROOT / "planner-config.json"
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
    recipe["tags"] = set(tags)
    return recipe


def load_recipes() -> list[dict]:
    recipes = []
    for path in sorted(RECIPES_DIR.glob("*.md")):
        if path.name in IGNORE_FILES:
            continue
        if r := parse_frontmatter(path):
            recipes.append(r)
    return recipes


def load_themes() -> list[dict]:
    """Optional per-weekday themes from planner-config.json.

    Theme fields: weekday (0=Mon..6=Sun, or null for a weekly quota), name,
    slot, require_tags (recipe must have all), optional count (default 1)."""
    if not CONFIG_PATH.exists():
        return []
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f).get("themes", [])


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


def build_pool(
    recipes: list[dict],
    slot: str,
    max_time: int | None,
    exclude_tags: set[str],
    require_tags: set[str] | None = None,
) -> list[dict]:
    pool = [r for r in recipes if r.get("dish_type") == slot]
    if require_tags:
        # strict: a themed slot must genuinely match its tags, else empty pool
        pool = [r for r in pool if require_tags <= r["tags"]]
    # skip unfilled recipes (missing time metadata) unless nothing else exists
    if filled := [r for r in pool if r.get("time_total_min", 0) > 0]:
        pool = filled
    if max_time is not None:
        pool = [r for r in pool if r.get("time_total_min", 0) <= max_time]
    if exclude_tags:
        pool = [r for r in pool if not exclude_tags & r["tags"]]
    return pool


def load_preferences() -> dict:
    """Optional slot preferences from planner-config.json, e.g.:

    preferences:
      carb:
        prefer_tags: [rice, staple, bulgur]   # recipes with these tags rank first
        defer_tags: [potatoes, roasted]       # recipes with these tags rank later
        penalty: 3.0                          # extra score weight for deferred recipes
    """
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return json.load(f).get("preferences", {})


def pick_best(
    pool: list[dict],
    used: set[str],
    recency: dict[str, date],
    today: date,
    rng: random.Random,
    prefer_tags: set[str] | None = None,
    defer_tags: set[str] | None = None,
    defer_penalty: float = 3.0,
) -> dict | None:
    """Best unused pick: rarely-cooked and quick first, with jitter.
    prefer_tags recipes rank ahead; defer_tags recipes get a penalty."""
    candidates = [r for r in pool if r["slug"] not in used] or pool
    if not candidates:
        return None

    def pref_score(r: dict) -> float:
        s = 0.0
        if prefer_tags and (prefer_tags & r["tags"]):
            s -= defer_penalty
        if defer_tags and (defer_tags & r["tags"]):
            s += defer_penalty
        return s

    return min(candidates, key=lambda r: (
        recency_penalty(r["slug"], recency, today) + pref_score(r) + rng.random(),
        r.get("time_total_min", 0),
    ))


def compose_week(
    recipes: list[dict],
    slots: list[str],
    days: int,
    recency: dict[str, date],
    themes: list[dict],
    once_rules: set[str],
    max_time: int | None,
    exclude_tags: set[str],
    seed: int | None,
    today: date,
    preferences: dict | None = None,
) -> tuple[list[list[dict | None]], list[str | None]]:
    """Returns (days x slots picks, day labels), honoring weekday themes and quotas."""
    rng = random.Random(seed)
    preferences = preferences or {}

    # per-slot tag preferences (e.g. prefer rice over potatoes for carb)
    slot_prefs: dict[str, dict] = {}
    for slot, prefs in (preferences or {}).items():
        if isinstance(prefs, dict):
            slot_prefs[slot] = prefs

    def pref_args(slot: str) -> dict:
        p = slot_prefs.get(slot, {})
        return {
            "prefer_tags": set(p.get("prefer_tags", [])) or None,
            "defer_tags": set(p.get("defer_tags", [])) or None,
            "defer_penalty": float(p.get("penalty", 3.0)),
        }

    day_themes: dict[int, list[dict]] = defaultdict(list)
    quota_themes: list[dict] = []
    for t in themes:
        # weekday themes: single "weekday" or a "weekdays" list
        weekdays = t.get("weekdays")
        if weekdays is None and t.get("weekday") is not None:
            weekdays = [t["weekday"]]
        if weekdays:
            for wd in weekdays:
                day_themes[int(wd)].append(t)
        else:
            quota_themes.append(t)
    quota_remaining: dict[str, int] = {t["name"]: int(t.get("count", 1)) for t in quota_themes}

    labels: list[str | None] = [None] * days

    # recipes reserved for specific weekdays by themes (reserve != false);
    # weekday-theme recipes stay exclusive to their themed day
    reserved_slugs: set[str] = set()
    for wd, tlist in day_themes.items():
        for t in tlist:
            if t.get("reserve", True):
                pool = build_pool(recipes, t["slot"], max_time, exclude_tags,
                                  require_tags=set(t.get("require_tags", [])))
                reserved_slugs |= {r["slug"] for r in pool}

    # base rotation per slot (excluding reserved recipes)
    rotation: dict[str, list[dict]] = {}
    for slot in slots:
        pool = [r for r in build_pool(recipes, slot, max_time, exclude_tags)
                if r["slug"] not in reserved_slugs]
        rng.shuffle(pool)
        pool.sort(key=lambda r: (recency_penalty(r["slug"], recency, today) + rng.random(),
                                 r.get("time_total_min", 0)))
        rotation[slot] = pool

    used: dict[str, set[str]] = defaultdict(set)
    week: list[list[dict | None]] = []

    for day_idx in range(days):
        night: list[dict | None] = [None] * len(slots)
        themed_slots: set[str] = set()

        def apply_theme(t: dict) -> None:
            slot = t["slot"]
            if slot not in slots or slot in themed_slots:
                return
            pos = slots.index(slot)
            pool = build_pool(recipes, slot, max_time, exclude_tags,
                              require_tags=set(t.get("require_tags", [])))
            pick = pick_best(pool, used[slot], recency, today, rng, **pref_args(slot))
            # no fallback: if the theme pool is empty/exhausted, leave the slot
            # to the base rotation rather than mislabeling an off-theme pick
            if pick:
                night[pos] = pick
                used[slot].add(pick["slug"])
                themed_slots.add(slot)
                labels[day_idx] = labels[day_idx] or t["name"]

        # 1) weekday-pinned themes (e.g. Fish Tuesday)
        for t in day_themes.get(day_idx, []):
            apply_theme(t)

        # 2) weekly-quota themes (e.g. one vegetarian night), first free day wins
        for t in quota_themes:
            name = t["name"]
            if quota_remaining.get(name, 0) <= 0:
                continue
            slot = t["slot"]
            pos = slots.index(slot) if slot in slots else None
            if pos is None or night[pos] is not None:
                continue
            req = set(t.get("require_tags", []))
            pool = build_pool(recipes, slot, max_time, exclude_tags, require_tags=req)
            pool = [r for r in pool if r["slug"] not in used[slot]]
            if not pool:
                continue
            pick = pick_best(pool, used[slot], recency, today, rng, **pref_args(slot))
            if pick:
                night[pos] = pick
                used[slot].add(pick["slug"])
                themed_slots.add(slot)
                quota_remaining[name] -= 1
                labels[day_idx] = labels[day_idx] or name

        # 3) fill remaining slots from base rotation
        for pos, slot in enumerate(slots):
            if night[pos] is not None:
                continue
            pool = rotation.get(slot, [])
            pick = pick_best(pool, used[slot], recency, today, rng, **pref_args(slot))
            if pick:
                night[pos] = pick
                used[slot].add(pick["slug"])
                if slot in once_rules:
                    rotation[slot] = [r for r in rotation[slot] if r["slug"] != pick["slug"]]
                else:
                    rotation[slot] = [r for r in rotation[slot] if r["slug"] != pick["slug"]] + [pick]

        week.append(night)

    return week, labels


def fmt_minutes(m: int) -> str:
    if m >= 60 and m % 60 == 0:
        return f"{m // 60}h"
    if m >= 60:
        return f"{m // 60}h{m % 60:02d}"
    return f"{m} min"


def render_menu_page(
    start: date,
    week: list[list[dict | None]],
    slots: list[str],
    plan_date: date,
    day_labels: list[str | None],
) -> str:
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
    all_picks: list[dict | None] = []
    for i, night in enumerate(week):
        day = DAY_NAMES[i % 7]
        lbl = day_labels[i] if i < len(day_labels) else None
        if lbl:
            day = f"{day} ({lbl})"
        cells = []
        for r in night:
            if r is None:
                cells.append("-")
                continue
            all_picks.append(r)
            total = r.get("time_total_min", 0)
            cells.append(f"[{r['title']}](../recipes/{r['slug']}.md) ({fmt_minutes(total)})")
        lines.append(f"| {day} | " + " | ".join(cells) + " |")
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
    ap.add_argument("--no-salad", action="store_true", help="omit the salad slot")
    ap.add_argument("--no-themes", action="store_true", help="ignore planner-config.json themes")
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
    once_rules = set()
    if args.carb_once and "carb" in slots:
        once_rules.add("carb")
    if args.protein_once and "protein" in slots:
        once_rules.add("protein")

    themes = [] if args.no_themes else load_themes()

    MENUS_DIR.mkdir(parents=True, exist_ok=True)
    menu_path = MENUS_DIR / f"menu-{start.isoformat()}.md"
    if menu_path.exists() and not args.overwrite:
        print(f"{menu_path} already exists; use --overwrite to replace it")
        return 1

    recipes = load_recipes()
    recency = load_recency()

    # sanity: every slot must have at least one eligible recipe
    for slot in slots:
        if not build_pool(recipes, slot, args.max_time, set(args.exclude_tag)):
            print(f"Error: no eligible recipes for dish_type slot: {slot}")
            return 1

    # theme sanity: warn about empty theme pools
    for t in themes:
        pool = build_pool(recipes, t["slot"], args.max_time, set(args.exclude_tag),
                          require_tags=set(t.get("require_tags", [])))
        if not pool:
            print(f"Warning: theme '{t['name']}' has no eligible recipes "
                  f"(tags: {t.get('require_tags')}) - will fall back on that day")

    week, day_labels = compose_week(
        recipes, slots, args.days, recency, themes,
        once_rules, args.max_time, set(args.exclude_tag), args.seed, today,
        preferences=load_preferences(),
    )

    menu_path.write_text(render_menu_page(start, week, slots, today, day_labels), encoding="utf-8")
    (MENUS_DIR / "index.md").write_text(render_index(MENUS_DIR), encoding="utf-8")

    counts: Counter = Counter()
    for night in week:
        for r in night:
            if r is not None:
                counts[r.get("dish_type", "?")] += 1
    print(f"Wrote {menu_path} ({args.days} nights x {len(slots)} slots)")
    print(f"Slot fill counts: {dict(counts)}")
    for t in themes:
        wds = t.get("weekdays") or ([t["weekday"]] if t.get("weekday") is not None else [])
        if wds:
            when = " + ".join(DAY_NAMES[int(w)] for w in wds)
        else:
            when = f"x{t.get('count', 1)}/week"
        print(f"  theme: {t['name']} - {when} ({t['slot']}: {', '.join(t.get('require_tags', []))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())