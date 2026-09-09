# family-recipes

Family recipe book (public) + simple cooking log + tooling.

Site (GitHub Pages): https://taylanpince.github.io/family-recipes/

## Weekly menu planning

House rule: nightly menus are **1 protein + 1 carb + a salad**. Each recipe
frontmatter carries a `dish_type` (protein / carb / salad / soup / breakfast /
side), and the planner composes nights as permutations of these slots.

```bash
.venv/bin/python scripts/plan_week.py --seed 7
```

Writes `docs/menus/menu-<week>.md` (day-by-day table + rough grocery list)
and updates the menus index. Avoids recently-cooked recipes from
`log/cooked.csv` and skips recipes still missing time metadata when the slot
has alternatives. Useful flags:

- `--days 5` - plan only weeknights
- `--start YYYY-MM-DD` - plan a specific week
- `--seed N` - reproducible plans
- `--no-salad` - omit the salad slot
- `--carb-once` / `--protein-once` - never repeat that slot within the week
- `--slots "protein,carb,salad,soup"` - custom nightly slot list
- `--no-themes` - ignore weekly themes for one run

### Weekly themes

`planner-config.json` (repo root) pins themed nights. Current setup:

| Theme | When | Rule |
|---|---|---|
| Fish Night | Tuesday | protein must be tagged `fish` (fresh fishmonger day) |
| Cookout | Friday | protein must be tagged `bbq` (lamb chops, steaks, köfte) |
| Vegetarian Night | 1x/week | protein must be tagged `vegetarian` |

Weekday themes reserve their tagged recipes exclusively for that day - the
planner won't schedule BBQ dishes on other days. Set `"reserve": false` on a
theme to allow its recipes in the general rotation.
