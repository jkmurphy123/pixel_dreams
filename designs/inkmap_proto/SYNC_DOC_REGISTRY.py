"""Regenerate the design doc's section 6 JSON block from the LIVE registry.

The doc used to carry a hand-written copy of the inkmap registry entry. A hand-written copy of a
schema drifts the moment anyone edits the schema, so the block is generated from `modes_registry.json`
instead, and this script is how it gets regenerated:

    .venv/bin/python designs/inkmap_proto/SYNC_DOC_REGISTRY.py

It rewrites only the fenced json block under "## 6." and prints the line count either side.
"""
import io
import json
import os
import re
import sys

BASE = '/mnt/ssd/projects/pixel_dreams'
DOC = os.path.join(BASE, 'designs', 'INK_FANTASY_MAP_DESIGN.md')
REG = os.path.join(BASE, 'modes_registry.json')


def main():
    registry = json.load(io.open(REG, encoding='utf-8'))
    entry = {'types': {'inkmap': registry['types']['inkmap']}}

    doc = io.open(DOC, encoding='utf-8').read()
    heading = doc.index('## 6.')
    fence = doc.index('```json', heading)
    close = doc.index('\n```', fence + 7)
    block = '```json\n' + json.dumps(entry, indent=2, ensure_ascii=False) + '\n'
    updated = doc[:fence] + block + doc[close:]

    before = len(doc.splitlines())
    after = len(updated.splitlines())
    io.open(DOC, 'w', encoding='utf-8').write(updated)
    print('section 6 regenerated from the registry: %d -> %d lines' % (before, after))
    print('params in the block: %d' % len(entry['types']['inkmap']['params']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
