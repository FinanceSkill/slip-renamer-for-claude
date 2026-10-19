#!/usr/bin/env python3
"""Scan slips and receipts: real file type, content hash, text layer, and naming fields from known layouts.

usage: scan.py <file|folder|zip> ... --work <workdir> [--match REGEX]

Writes
  <workdir>/scan.json        one record per file: id, path, kind, sha256, layout, fields, needs_reading, notes
                             (id = 'h' + first 10 hex of the content hash, so it stays the same across rescans
                             and manual.json entries can never land on another file)
  <workdir>/text/<id>.txt    the text layer of each PDF that has one
Zips are extracted into <workdir>/raw/ (Thai file names decoded). Folders are scanned recursively.
--match keeps only files whose name matches REGEX (case-insensitive).
"""
import argparse, hashlib, json, logging, os, re, sys, zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parsers import parse, REQUIRED  # noqa: E402

logging.getLogger('pdfminer').setLevel(logging.ERROR)
EXTS = ('.pdf', '.jpg', '.jpeg', '.png', '.webp', '.heic', '.gif')
MAGIC = [(b'%PDF', 'pdf'), (b'\x89PNG', 'png'), (b'\xff\xd8\xff', 'jpg'), (b'GIF8', 'gif')]


def sniff(path):
    head = open(path, 'rb').read(16)
    for sig, kind in MAGIC:
        if head.startswith(sig):
            return kind
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'webp'
    if head[4:8] == b'ftyp':
        return 'heic'
    return 'unknown'


def zipname(info):
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode('cp437')
    for enc in ('utf-8', 'cp874'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return info.filename


def unzip(zpath, dest):
    out = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = zipname(info)
            parts = [p for p in name.split('/') if p not in ('', '.', '..')]
            if name.endswith('/') or '__MACOSX' in name or not parts:
                continue
            target = os.path.join(dest, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            pwds = [None] + [m.encode() for m in re.findall(r'PW\s*([0-9A-Za-z]+)', name + os.path.basename(zpath))]
            for pwd in pwds:
                try:
                    data = z.read(info, pwd=pwd)
                    break
                except RuntimeError:
                    data = None
            if data is None:
                print('SKIPPED (encrypted zip entry):', name)
                continue
            open(target, 'wb').write(data)
            out.append((target, f'{os.path.basename(zpath)}/{name}'))
    return out


def collect(inputs, work, match, recurse=True):
    files = []
    for p in inputs:
        p = os.path.abspath(os.path.expanduser(p))
        if os.path.isdir(p):
            for root, dirs, names in os.walk(p):
                files += [(os.path.join(root, n), None) for n in sorted(names)]
                if not recurse:
                    dirs.clear()
        elif p.lower().endswith('.zip'):
            files += unzip(p, os.path.join(work, 'raw', os.path.splitext(os.path.basename(p))[0]))
        else:
            files.append((p, None))
    rx = re.compile(match, re.I) if match else None
    return [(f, o) for f, o in files
            if f.lower().endswith(EXTS) and not os.path.basename(f).startswith('.')
            and (not rx or rx.search(os.path.basename(f)))]


def pdf_text(path):
    import pdfplumber
    pw = re.search(r'PW\s*([0-9A-Za-z]+)', os.path.basename(path))
    with pdfplumber.open(path, password=pw.group(1) if pw else None) as pdf:
        text = '\n'.join((pg.extract_text() or '') for pg in pdf.pages[:6])
    return text.replace('\x00', ' ').replace('\u2236', ':'), len(pdf.pages)  # some PDFs use NUL as a space


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('--work', required=True)
    ap.add_argument('--match')
    ap.add_argument('--no-recurse', action='store_true', help='scan only the top level of folders')
    a = ap.parse_args()
    os.makedirs(os.path.join(a.work, 'text'), exist_ok=True)
    records, seen, copies = [], {}, Counter()
    for path, origin in collect(a.inputs, a.work, a.match, not a.no_recurse):
        data = open(path, 'rb').read()
        sha = hashlib.sha256(data).hexdigest()
        copies[sha] += 1
        rid = 'h' + sha[:10] + (f'-{copies[sha]}' if copies[sha] > 1 else '')
        real = sniff(path)
        ext = os.path.splitext(path)[1].lower()
        r = {'id': rid, 'path': path, 'origin': origin or path, 'name': os.path.basename(path), 'real_type': real,
             'sha256': sha, 'kind': None, 'layout': None, 'fields': {}, 'read_by': None, 'needs_reading': True,
             'notes': [], 'duplicate_of': seen.get(sha)}
        seen.setdefault(sha, rid)
        if real != ext.lstrip('.').replace('jpeg', 'jpg') and not (real == 'heic' and ext == '.heic'):
            r['notes'].append(f'file is really {real}, not {ext}')
        if real == 'pdf':
            try:
                text, pages = pdf_text(path)
            except Exception as e:  # password-protected or broken
                r['kind'] = 'pdf-unreadable'
                r['notes'].append(f'cannot open PDF: {type(e).__name__}')
                records.append(r)
                continue
            if len(text.strip()) < 30:
                r['kind'] = 'pdf-image'
            else:
                r['kind'] = 'pdf-text'
                tf = os.path.join(a.work, 'text', f'{rid}.txt')
                open(tf, 'w', encoding='utf-8').write(text)
                r['text_file'] = tf
                layout, fields, notes = parse(text)
                r['layout'], r['fields'], r['notes'] = layout, fields, r['notes'] + notes
                if layout:
                    r['read_by'] = 'parser'
                missing = [k for k in REQUIRED if not fields.get(k)]
                r['needs_reading'] = bool(missing)
                if layout and missing:
                    r['notes'].append('parser missed: ' + ', '.join(missing))
        elif real in ('png', 'jpg', 'webp', 'gif', 'heic'):
            r['kind'] = 'image'
        else:
            r['kind'] = 'unknown'
            r['notes'].append('not a PDF or image')
        records.append(r)
    json.dump(records, open(os.path.join(a.work, 'scan.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    kinds = Counter(r['kind'] for r in records)
    layouts = Counter(r['layout'] or '(no parser)' for r in records if r['kind'] == 'pdf-text')
    dups = [r for r in records if r['duplicate_of']]
    need = [r for r in records if r['needs_reading'] and not r['duplicate_of']]
    print(f'{len(records)} files -> {a.work}/scan.json')
    print('  by kind:', dict(kinds))
    print('  text PDFs by layout:', dict(layouts))
    print(f'  duplicates (same content): {len(dups)}')
    for r in dups:
        print(f'    {r["name"]} = {next(x["name"] for x in records if x["id"] == r["duplicate_of"])}')
    print(f'  need reading: {len(need)} ({Counter(r["kind"] for r in need)})')
    for r in need[:40]:
        print(f'    {r["id"]} {r["kind"]:9} {r["name"]}  {"; ".join(r["notes"])}')


if __name__ == '__main__':
    main()
