#!/usr/bin/env python3
"""Normalize/upgrade recipe frontmatter.

Current focus:
- Ensure difficulty is one of easy|medium|hard.
- Ensure tags is a YAML list (not null).
- Optionally infer cuisine/tags/time_total_min/servings later.

Safe to run repeatedly.
"""

from __future__ import annotations

import re
from pathlib import Path

ALLOWED_DIFFICULTY = {"easy", "medium", "hard"}


def get_frontmatter_block(text: str) -> tuple[str, str, str] | None:
    if not text.startswith('---'):
        return None
    parts = text.split('---', 2)
    if len(parts) < 3:
        return None
    # parts[0] is empty before first ---
    fm = parts[1].strip('\n')
    rest = parts[2].lstrip('\n')
    return ('---\n' + fm + '\n---\n', fm, rest)


def set_key(fm: str, key: str, value_line: str) -> str:
    # replace existing key line or append
    pattern = re.compile(rf"^{re.escape(key)}:\s*.*$", re.M)
    if pattern.search(fm):
        return pattern.sub(value_line, fm)
    return fm.rstrip() + "\n" + value_line + "\n"


def normalize_file(path: Path) -> bool:
    text = path.read_text(encoding='utf-8', errors='ignore')
    block = get_frontmatter_block(text)
    if not block:
        return False

    wrapper, fm, rest = block
    changed = False

    # difficulty
    m = re.search(r'^difficulty:\s*(\S+)', fm, re.M)
    if m:
        diff = m.group(1).strip().strip('"')
        if diff not in ALLOWED_DIFFICULTY:
            fm = set_key(fm, 'difficulty', 'difficulty: easy')
            changed = True
    else:
        fm = set_key(fm, 'difficulty', 'difficulty: easy')
        changed = True

    # tags
    if re.search(r'^tags:\s*\[\s*\]$', fm, re.M) is None and re.search(r'^tags:\s*$', fm, re.M):
        fm = set_key(fm, 'tags', 'tags: []')
        changed = True

    # time_total_min + servings as ints
    for k in ('time_total_min', 'servings'):
        m = re.search(rf'^{k}:\s*(.+)$', fm, re.M)
        if m:
            val = m.group(1).strip().strip('"')
            if not val.isdigit():
                fm = set_key(fm, k, f'{k}: 0')
                changed = True
        else:
            fm = set_key(fm, k, f'{k}: 0')
            changed = True

    if not changed:
        return False

    new = '---\n' + fm.strip('\n') + '\n---\n\n' + rest
    path.write_text(new, encoding='utf-8')
    return True


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    recipes = root / 'docs' / 'recipes'
    ignore = {'index.md', 'conventions.md', '_template.md'}
    changed = 0
    for f in recipes.glob('*.md'):
        if f.name in ignore:
            continue
        if normalize_file(f):
            changed += 1
    print(f'Normalized {changed} recipe files')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
