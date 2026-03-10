#!/usr/bin/env python3
"""Generate docs/log.md from log/cooked.csv (last N entries).

Keeps docs/log.md as a friendly view, while cooked.csv remains the source of truth.
"""

from __future__ import annotations

import csv
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    csv_path = root / "log" / "cooked.csv"
    out_path = root / "docs" / "log.md"

    rows = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                if not row.get("date"):
                    continue
                rows.append(row)

    # newest first
    rows = list(reversed(rows))
    rows = rows[:50]

    lines = [
        "# Cooking log",
        "",
        "Source of truth: `log/cooked.csv` (append-only).",
        "",
        "## Latest",
        "",
    ]

    if not rows:
        lines.append("(No entries yet.)")
    else:
        for row in rows:
            d = row.get("date", "").strip()
            slug = row.get("recipe_slug", "").strip()
            notes = (row.get("notes") or "").strip()
            rating = (row.get("rating") or "").strip()

            extra = []
            if rating:
                extra.append(f"rating: {rating}/5")
            if notes:
                extra.append(notes)
            suffix = " — " + "; ".join(extra) if extra else ""

            lines.append(f"- **{d}** — `{slug}`{suffix}")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
