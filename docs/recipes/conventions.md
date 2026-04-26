# Conventions

## Recipe files

- Each recipe is a single Markdown file under `docs/recipes/`.
- Filename should match the recipe **slug**:
  - Example: `bulgur-pilav.md`

## Frontmatter schema

Every recipe starts with YAML frontmatter.

Required:

- `slug`: stable identifier (kebab-case)
- `title`: human title

Recommended:

- `tags`: list of strings (e.g. `weeknight`, `kid-friendly`, `vegetarian`, `turkish`)
- `cuisine`: string
- `difficulty`: `easy|medium|hard`
- `time_total_min`: integer
- `servings`: integer
- `ingredients`: list of strings (free-form)

Example:

```yaml
---
slug: bulgur-pilav
title: Bulgur Pilav
cuisine: Turkish
difficulty: easy
time_total_min: 35
servings: 4
tags:
  - weeknight
  - turkish
ingredients:
  - bulgur
  - onion
  - tomato paste
  - stock
---
```

## Body sections

Use these headings (lightly enforced by convention only):

- `## Ingredients` (optional in the handwritten body if captured in frontmatter)
- `## Steps`
- `## Notes` (substitutions, variations, etc.)

## Published page rendering

- The script `scripts/render_recipe_metadata.py` renders visible recipe metadata from frontmatter into each recipe page.
- That generated block includes basic details plus the `ingredients` list.
- Do not hand-edit the generated metadata block inside recipe files, rerun the script instead after frontmatter changes.
