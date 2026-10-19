#!/usr/bin/env python3
"""Plan the new names: show naming options, or build and check a rename plan.

usage:
  plan.py <workdir> --suggest
  plan.py <workdir> --template "<template>" --dest <folder> [--by-month]

Fields come from scan.json (parsers), overridden by every <workdir>/manual*.json written by a reader.
<workdir>/check*.json holds an independent second reading of image files.

Placeholders: {type} {DD} {MM} {YYYY} {YY} {date} {vendor} {vendor_full} {party} {amount} {amount_plain}
              {currency} {doc_no} {description} {bank}

Each file gets a status:
  ok         the name is built and every date, amount and document number in it was found in the
             file's text (text PDFs) or matched the second reading (images)
  review     a value is missing, a check failed, or a reader marked it "skip": copied to _review/ under
             its original name
  duplicate  same content as an earlier file: not copied
Writes <workdir>/plan.csv and plan.json, prints a summary.
"""
import argparse, csv, glob, json, os, re, sys
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ['type', 'date', 'vendor', 'vendor_full', 'party', 'amount', 'currency', 'doc_no', 'description', 'bank']
CANDIDATES = [
    ('type-date-vendor-amount', '{type}-{DD}-{MM}-{YYYY}-{vendor}-{amount} {currency}'),
    ('date first, sorts by date', '{YYYY}-{MM}-{DD}_{vendor}_{currency}{amount_plain}_{doc_no}'),
    ('type-vendor-amount', '{type}-{vendor}-{amount_plain}{currency}'),
    ('with the other party', '{type}-{DD}-{MM}-{YYYY}-{vendor}-{party}-{amount} {currency}'),
]
TH_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
TH_MONTHS_FULL = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม',
                  'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม']
EN_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
             'November', 'December']
BAD = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def load(work):
    records = json.load(open(os.path.join(work, 'scan.json'), encoding='utf-8'))
    manual, check = {}, {}
    for p in sorted(glob.glob(os.path.join(work, 'manual*.json'))):
        manual.update(json.load(open(p, encoding='utf-8')))
    for p in sorted(glob.glob(os.path.join(work, 'check*.json'))):
        check.update(json.load(open(p, encoding='utf-8')))
    for r in records:
        m = manual.get(r['id'])
        if m:
            r['fields'] = {**r['fields'], **{k: v for k, v in m.items() if k in FIELDS and v not in (None, '')}}
            r['read_by'] = ('image' if r['kind'] != 'pdf-text' else 'reader') if r['read_by'] != 'parser' else 'parser+reader'
            if m.get('skip'):
                r['skip'] = m['skip']
            r['notes'] = r['notes'] + list(m.get('notes', []))
        r['check'] = check.get(r['id'])
        if r['kind'] == 'pdf-text':
            r['text'] = open(r['text_file'], encoding='utf-8').read()
    return records


def amount_parts(printed):
    s = re.sub(r'[^\d.,-]', '', str(printed or ''))
    if not s:
        return None
    # "1.234,56" style: comma is the decimal mark when it comes last and is followed by 2 digits
    if re.search(r',\d{2}$', s) and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    s = s.replace(',', '')
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    decimals = len(s.split('.')[1]) if '.' in s else 0
    return d, f'{d:,.{decimals}f}', f'{d:.{decimals}f}'


def values(f):
    v = {k: str(f.get(k) or '').strip() for k in FIELDS}
    try:
        y, m, d = map(int, v['date'].split('-'))
        dt = date(y, m, d)
        v.update(DD=f'{d:02d}', MM=f'{m:02d}', YYYY=f'{y}', YY=f'{y % 100:02d}', date=dt.isoformat())
    except ValueError:
        v.update(DD='', MM='', YYYY='', YY='', date='')
    a = amount_parts(v['amount'])
    v['amount'], v['amount_plain'] = (a[1], a[2]) if a else ('', '')
    return v


def date_forms(iso):
    y, m, d = map(int, iso.split('-'))
    be = y + 543
    forms = {f'{EN_MONTHS[m-1]} {d}, {y}', f'{EN_MONTHS[m-1][:3]} {d}, {y}', f'{d} {EN_MONTHS[m-1]} {y}',
             f'{d} {EN_MONTHS[m-1][:3]} {y}', f'{d:02d}/{m:02d}/{y}', f'{d}/{m}/{y}', f'{m:02d}/{d:02d}/{y}',
             f'{y}-{m:02d}-{d:02d}', f'{d:02d}-{m:02d}-{y}', f'{d:02d}.{m:02d}.{y}', f'{y}/{m:02d}/{d:02d}',
             f'{d:02d}/{m:02d}/{y % 100:02d}', f'{d:02d}/{m:02d}/{be}', f'{d:02d}/{m:02d}/{be % 100:02d}',
             f'{d} {TH_MONTHS[m-1]} {be}', f'{d} {TH_MONTHS[m-1]} {be % 100:02d}', f'{d} {TH_MONTHS_FULL[m-1]} {be}',
             f'{d:02d} {EN_MONTHS[m-1]} {y}', f'{d:02d} {EN_MONTHS[m-1][:3]} {y}', f'{EN_MONTHS[m-1]} {d:02d}, {y}',
             f'{EN_MONTHS[m-1][:3]} {d:02d}, {y}',
             f'{d} {TH_MONTHS[m-1]} {y}', f'{d} {TH_MONTHS_FULL[m-1]} {y}', f'{d:02d} {TH_MONTHS[m-1]} {be % 100:02d}',
             f'{d:02d} {TH_MONTHS[m-1]} {be}', f'{d} sept {y}', f'sept {d}, {y}'}
    return {re.sub(r'\s+', ' ', x).lower() for x in forms}


def date_regexes(iso):
    """Each printed form as a regex with loose separators ("ก.ย." also matches "ก ย") and no digits
    either side, so "2/9/2026" can't match inside "12/9/2026"."""
    out = []
    for f in date_forms(iso):
        parts = [p for p in re.split(r'[\s.,/-]+', f) if p]
        out.append(re.compile(r'(?<!\d)' + r'[\s.,/-]*'.join(map(re.escape, parts)) + r'(?!\d)'))
    return out


def text_checks(r, v, used):
    """Every date, amount and document number used in the name must be printed in the file."""
    t = re.sub(r'\s+', ' ', r['text']).lower()
    problems = []
    if 'amount' in used or 'amount_plain' in used:
        plain = v['amount_plain']
        digits = re.sub(r'[,\s]', '', r['text'])
        alt = plain[:-3] if plain.endswith('.00') else plain + '.00' if '.' not in plain else None
        if not any(re.search(rf'(?<![\d.]){re.escape(x)}(?![\d])', digits) for x in filter(None, [plain, alt])):
            problems.append(f'amount {v["amount"]} not found in text')
    if used & {'date', 'DD', 'MM', 'YYYY', 'YY'} and v['date']:
        if not any(rx.search(t) for rx in date_regexes(v['date'])):
            problems.append(f'date {v["date"]} not found in text')
    if 'doc_no' in used:
        key = re.sub(r'[^0-9a-z]', '', v['doc_no'].lower())
        if key and key not in re.sub(r'[^0-9a-z]', '', t):
            problems.append(f'doc_no {v["doc_no"]} not found in text')
    return problems


def image_checks(r, v, used):
    """Images have no text to check against: the second reading must agree."""
    c = r.get('check')
    if not c:
        return ['read from an image with no second reading']
    cv, problems = values(c), []
    if used & {'amount', 'amount_plain'}:
        first, second = amount_parts(v['amount']), amount_parts(cv['amount'])
        if not first or not second or first[0] != second[0]:
            problems.append(f'amount: first reading {v["amount"]}, second reading {cv["amount"] or "-"}')
    if used & {'date', 'DD', 'MM', 'YYYY', 'YY'} and cv['date'] != v['date']:
        problems.append(f'date: first reading {v["date"]}, second reading {cv["date"] or "-"}')
    if 'doc_no' in used and re.sub(r'\W', '', cv['doc_no']).lower() != re.sub(r'\W', '', v['doc_no']).lower():
        problems.append(f'doc_no: first reading {v["doc_no"]}, second reading {cv["doc_no"] or "-"}')
    return problems


def clean(s, limit=60):
    s = re.sub(r'\s+', ' ', BAD.sub('-', s)).strip(' .-')
    return s[:limit].rstrip(' .-')


def render(template, v):
    used = set(re.findall(r'{(\w+)}', template))
    missing = [k for k in used if not v.get(k)]
    if missing:
        return None, used, missing
    name = template.format_map({k: clean(v[k]) for k in v})
    name = re.sub(r'\s+', ' ', name).strip(' .-_')
    while len(name.encode('utf-8')) > 230:  # leave room for the extension and a " (2)" suffix
        name = name[:-1]
    return name, used, []


def extension(r):
    ext = os.path.splitext(r['name'])[1]
    real = {'pdf': '.pdf', 'png': '.png', 'jpg': '.jpg', 'webp': '.webp', 'gif': '.gif', 'heic': '.heic'}.get(r['real_type'])
    if real and ext.lower().replace('.jpeg', '.jpg') != real:
        return real
    return ext


def suggest(records):
    live = [r for r in records if not r['duplicate_of']]
    print(f'{len(live)} files (duplicates excluded). Field coverage:')
    for k in FIELDS:
        n = sum(1 for r in live if r['fields'].get(k))
        print(f'  {k:12} {n:4d}/{len(live)}')
    unread = [r for r in live if any(not r['fields'].get(k) for k in ('date', 'vendor', 'amount', 'currency')) and not r.get('skip')]
    if unread:
        print(f'{len(unread)} files still miss date, vendor, amount or currency; read them first:',
              ', '.join(r['id'] for r in unread[:30]))
    picks, seen = [], set()
    for r in live:
        key = r['layout'] or r['kind'] + (r['read_by'] or '')
        if key not in seen and all(r['fields'].get(k) for k in ('date', 'vendor', 'amount', 'currency')):
            seen.add(key)
            picks.append(r)
    print('\nCandidate templates, rendered on real files:')
    for label, t in CANDIDATES:
        names = [render(t, values(r['fields']))[0] for r in live]
        built = [n.lower() for n in names if n]
        clashes = len(built) - len(set(built))
        print(f'\n  [{label}]  {t}')
        print(f'     names built for {len(built)}/{len(live)} files; {clashes} would clash and get a " (2)" suffix')
        for r in picks[:4]:
            name, _, missing = render(t, values(r['fields']))
            print('    ', (name + extension(r)) if name else f'(missing {", ".join(missing)})', '  <-', r['name'])


def plan(records, template, dest, by_month, work):
    rows, taken = [], set()
    for r in records:
        v = values(r['fields'])
        status, reason, new = 'ok', '', ''
        if r['duplicate_of']:
            status, reason = 'duplicate', 'same content as ' + next(x['name'] for x in records if x['id'] == r['duplicate_of'])
        elif r.get('skip'):
            status, reason = 'review', r['skip']
        else:
            name, used, missing = render(template, v)
            if missing:
                status, reason = 'review', 'missing ' + ', '.join(sorted(missing))
            else:
                problems = text_checks(r, v, used) if r['kind'] == 'pdf-text' else image_checks(r, v, used)
                if problems:
                    status, reason = 'review', '; '.join(problems)
                else:
                    sub = f'{v["YYYY"]}-{v["MM"]}' if by_month and v['YYYY'] else ''
                    base, ext, n = name, extension(r), 1
                    while True:
                        new = os.path.join(sub, base + (f' ({n})' if n > 1 else '') + ext)
                        if new.lower() not in taken:
                            break
                        n += 1
                    taken.add(new.lower())
                    if n > 1:
                        reason = 'name taken: numbered'
        if status == 'review':
            new = os.path.join('_review', r['name'])
            n = 1
            while new.lower() in taken:
                n += 1
                stem, ext = os.path.splitext(r['name'])
                new = os.path.join('_review', f'{stem} ({n}){ext}')
            taken.add(new.lower())
        rows.append({'id': r['id'], 'status': status, 'reason': reason, 'original': r['origin'], 'source_path': r['path'],
                     'new': new if status != 'duplicate' else '', **{k: r['fields'].get(k, '') for k in FIELDS},
                     'read_by': r['read_by'] or '', 'notes': '; '.join(r['notes']), 'sha256': r['sha256']})
    with open(os.path.join(work, 'plan.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    json.dump({'template': template, 'dest': os.path.abspath(os.path.expanduser(dest)), 'by_month': by_month},
              open(os.path.join(work, 'plan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    c = Counter(r['status'] for r in rows)
    print(f'plan: {dict(c)} -> {work}/plan.csv   dest: {dest}')
    for r in [x for x in rows if x['status'] == 'review']:
        print(f'  REVIEW {r["id"]} {os.path.basename(r["original"])}: {r["reason"]}')
    print('sample:')
    for r in [x for x in rows if x['status'] == 'ok'][:8]:
        print(f'  {os.path.basename(r["original"])}  ->  {r["new"]}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('work')
    ap.add_argument('--suggest', action='store_true')
    ap.add_argument('--template')
    ap.add_argument('--dest')
    ap.add_argument('--by-month', action='store_true')
    a = ap.parse_args()
    records = load(a.work)
    if a.suggest:
        return suggest(records)
    if not (a.template and a.dest):
        sys.exit('--template and --dest are required (or use --suggest)')
    bad = set(re.findall(r'{(\w+)}', a.template)) - set(values({}))
    if bad:
        sys.exit(f'unknown placeholder(s): {", ".join(sorted(bad))}')
    plan(records, a.template, a.dest, a.by_month, a.work)


if __name__ == '__main__':
    main()
