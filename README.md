# family-recipes

Family recipe book (public) + simple cooking log + tooling.

Site (GitHub Pages): https://taylanpince.github.io/family-recipes/

## Weekly menu planning

Generate a dinner plan for the week:

```bash
.venv/bin/python scripts/plan_week.py --seed 7
```

Writes `docs/menus/menu-<week>.md` (day-by-day table + rough grocery list)
and updates the menus index. Skips recently-cooked recipes from
`log/cooked.csv`, excludes breakfast/side/pickle recipes by default, and
skips recipes still missing time metadata (use `--allow-unfilled` to include).
Useful flags: `--days 5`, `--max-time 60`, `--include-tag fish`, `--start YYYY-MM-DD`.
