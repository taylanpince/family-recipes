#!/usr/bin/env python3
"""Append a cooking log entry to log/cooked.csv.

Usage:
  scripts/log_cook.py <recipe_slug> [--date YYYY-MM-DD] [--notes "..."] [--rating 1-5]

This is intentionally simple: append-only CSV, git-friendly.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date as date_cls
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("recipe_slug")
    p.add_argument("--date", dest="date", default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--notes", default="")
    p.add_argument("--rating", type=int, default=None)
    args = p.parse_args()

    d = args.date or date_cls.today().isoformat()
    rating = "" if args.rating is None else str(args.rating)

    root = Path(__file__).resolve().parents[1]
    log_path = root / "log" / "cooked.csv"

    # ensure header exists
    if not log_path.exists():
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("date,recipe_slug,notes,rating\n", encoding="utf-8")

    with log_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([d, args.recipe_slug, args.notes, rating])

    print(f"Logged: {d},{args.recipe_slug}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
