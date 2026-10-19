#!/usr/bin/env python3
"""Copy files to their planned names and write the summary CSV. Originals are never moved or changed.

usage: apply.py <workdir>

Reads <workdir>/plan.csv and plan.json (from plan.py). Copies "ok" files to <dest>/<new>, "review" files to
<dest>/_review/ under their original names, skips duplicates. An existing file at the target is never
overwritten: an identical one counts as already copied, a different one gets a " (n)" suffix.
Writes <dest>/summary.csv (UTF-8 with BOM, so Thai shows correctly in Excel).
"""
import csv, hashlib, json, os, shutil, sys
from collections import Counter

STATUS = {'ok': 'renamed', 'review': 'review', 'duplicate': 'duplicate'}


def sha(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def free_target(path, digest):
    """Return (target, already_there)."""
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        if sha(path) == digest:
            return path, True
        n += 1
        path = f'{stem} ({n}){ext}'
    return path, False


def main():
    work = sys.argv[1]
    meta = json.load(open(os.path.join(work, 'plan.json'), encoding='utf-8'))
    dest = meta['dest']
    rows = list(csv.DictReader(open(os.path.join(work, 'plan.csv'), encoding='utf-8-sig')))
    os.makedirs(dest, exist_ok=True)
    out, counts = [], Counter()
    for r in rows:
        new = ''
        if r['status'] in ('ok', 'review'):
            target, already = free_target(os.path.join(dest, r['new']), r['sha256'])
            if not already:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(r['source_path'], target)
            new = os.path.relpath(target, dest)
            if new != r['new']:
                r['notes'] = '; '.join(filter(None, [r['notes'], 'target existed: numbered']))
            if already:
                r['notes'] = '; '.join(filter(None, [r['notes'], 'identical file already at target']))
        counts[STATUS[r['status']]] += 1
        out.append({'Status': STATUS[r['status']], 'New File': new, 'Original File': r['original'],
                    'Type': r['type'], 'Date': r['date'], 'Vendor': r['vendor'], 'Party': r['party'],
                    'Amount': r['amount'], 'Currency': r['currency'], 'Doc No': r['doc_no'],
                    'Description': r['description'], 'Read By': r['read_by'],
                    'Reason / Notes': '; '.join(filter(None, [r['reason'], r['notes']]))})
    summary = os.path.join(dest, 'summary.csv')
    n = 1
    while os.path.exists(summary):
        n += 1
        summary = os.path.join(dest, f'summary ({n}).csv')
    with open(summary, 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f'{dict(counts)} -> {dest}')
    print('summary:', summary)


if __name__ == '__main__':
    main()
