"""Tests for slip-renamer, on synthetic documents only (never real receipts).

Run: python3 -m unittest discover tests
"""
import csv, json, os, subprocess, sys, tempfile, unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'skills', 'slip-renamer', 'scripts')
sys.path.insert(0, SCRIPTS)
import parsers  # noqa: E402

TEMPLATE = '{type}-{DD}-{MM}-{YYYY}-{vendor}-{amount} {currency}'


def make_pdf(path, lines):
    """A minimal one-page PDF with a real text layer (Helvetica, ASCII only)."""
    esc = lambda s: s.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    content = 'BT /F1 10 Tf 50 750 Td 14 TL ' + ' '.join(f'({esc(l)}) Tj T*' for l in lines) + ' ET'
    objs = ['<< /Type /Catalog /Pages 2 0 R >>', '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R '
            '/Resources << /Font << /F1 5 0 R >> >> >>',
            f'<< /Length {len(content)} >>\nstream\n{content}\nendstream',
            '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = b'%PDF-1.4\n', []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f'{i} 0 obj\n{o}\nendobj\n'.encode()
    xref = len(out)
    out += f'xref\n0 {len(objs) + 1}\n0000000000 65535 f \n'.encode()
    out += b''.join(f'{o:010d} 00000 n \n'.encode() for o in offsets)
    out += f'trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    with open(path, 'wb') as f:
        f.write(out)


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


def read_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def read_csv(path):
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def dump(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


STRIPE = ['Receipt', 'Invoice number ABCD1234 0001', 'Receipt number 1234 5678', 'Date paid September 2, 2026',
          'Acme Cloud, Inc. (@acme) Bill to', '$49.00 paid on September 2, 2026', 'Total $49.00']


class ParserTest(unittest.TestCase):
    def test_stripe_receipt(self):
        layout, f, notes = parsers.parse('\n'.join(STRIPE))
        self.assertEqual(layout, 'stripe-receipt')
        self.assertEqual((f['date'], f['vendor'], f['amount'], f['currency'], f['doc_no']),
                         ('2026-09-02', 'Acme Cloud', '49.00', 'USD', '1234-5678'))
        self.assertIn('currency taken as USD from the $ sign', notes)

    def test_yen_without_code_is_left_open(self):
        _, f, notes = parsers.parse('Receipt number 1 2\nDate paid May 1, 2026\nX Ltd Bill to\n¥459 paid on May 1, 2026')
        self.assertNotIn('currency', f)
        self.assertTrue(any('JPY or CNY' in n for n in notes))

    def test_tripcom_flight_wrapped_route(self):
        text = '\n'.join(['Trip.com Travel Singapore Pte. Ltd.', 'Booking No. 1111222233334444',
                          'Date of Booking: 17:37, August 18, 2026 (GMT+8)', 'Contact Name JANE DOE', 'Flights',
                          'Ho Chi Minh City - Kuala September 6, 2026 Economy class', 'Lumpur', 'Example Air', 'AK521',
                          'Total (Visa credit card 123456***78) THB 2,280.00'])
        layout, f, _ = parsers.parse(text)
        self.assertEqual(layout, 'tripcom-flight')
        self.assertEqual(f['description'], 'Flight Ho Chi Minh City - Kuala Lumpur')
        self.assertEqual((f['date'], f['amount'], f['currency'], f['party']), ('2026-08-18', '2,280.00', 'THB', 'JANE DOE'))

    def test_tripcom_thai_hotel_paid_total(self):
        text = '\n'.join(['TRIP.COM TRAVEL SINGAPORE PTE. LTD.', 'หมายเลขการจอง: 1111222233334444',
                          'วนั ชาํ ระเงนิ : 18 ส.ค. 2026 (UTC+8)', 'โรงแรม Example Hotel', 'ยอดรวม PLN637',
                          'สว่ นลด -PLN34.25', 'ยอดชาํ ระทงั หมด (บตั รเดบติ MasterCard****1234) PLN602.75'])
        layout, f, _ = parsers.parse(text)
        self.assertEqual(layout, 'tripcom-hotel-th')
        self.assertEqual((f['date'], f['amount'], f['currency']), ('2026-08-18', '602.75', 'PLN'))


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.inp, self.work, self.dest = f'{d}/in', f'{d}/work', f'{d}/out'
        os.makedirs(self.inp)
        make_pdf(f'{self.inp}/acme.pdf', STRIPE)
        make_pdf(f'{self.inp}/acme copy.pdf', STRIPE)  # same bytes: a duplicate
        make_pdf(f'{self.inp}/other.pdf', ['Invoice from Foo Services', 'Paid 12 October 2026', 'Amount due THB 1,500.00',
                                           'Ref FOO-77'])
        from PIL import Image
        Image.new('RGB', (40, 20), 'white').save(f'{self.inp}/slip.png')

    def tearDown(self):
        self.tmp.cleanup()

    def scan(self):
        res = run('scan.py', self.inp, '--work', self.work)
        self.assertEqual(res.returncode, 0, res.stderr)
        return {r['name']: r for r in read_json(f'{self.work}/scan.json')}

    def plan(self):
        res = run('plan.py', self.work, '--template', TEMPLATE, '--dest', self.dest, '--by-month')
        self.assertEqual(res.returncode, 0, res.stderr)
        return {os.path.basename(r['original']): r for r in read_csv(f'{self.work}/plan.csv')}

    def test_end_to_end(self):
        recs = self.scan()
        self.assertEqual(recs['acme.pdf']['layout'], 'stripe-receipt')
        self.assertFalse(recs['acme.pdf']['needs_reading'])
        self.assertTrue(recs['acme copy.pdf']['duplicate_of'] or recs['acme.pdf']['duplicate_of'])
        self.assertTrue(recs['other.pdf']['needs_reading'])
        self.assertEqual(recs['slip.png']['kind'], 'image')
        dump({recs['other.pdf']['id']: {'type': 'Invoice', 'date': '2026-10-12', 'vendor': 'Foo Services',
                                        'amount': '1,500.00', 'currency': 'THB', 'doc_no': 'FOO-77'},
              recs['slip.png']['id']: {'type': 'Slip', 'date': '2026-10-05', 'vendor': 'Shop A', 'amount': '300.00',
                                       'currency': 'THB'}}, f'{self.work}/manual.json')
        dump({recs['slip.png']['id']: {'date': '2026-10-05', 'amount': '300.00'}}, f'{self.work}/check.json')
        plan = self.plan()
        self.assertEqual(plan['other.pdf']['new'], os.path.join('2026-10', 'Invoice-12-10-2026-Foo Services-1,500.00 THB.pdf'))
        self.assertEqual(plan['slip.png']['status'], 'ok')
        self.assertEqual(sorted(r['status'] for r in plan.values()), ['duplicate', 'ok', 'ok', 'ok'])
        res = run('apply.py', self.work)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(os.path.exists(f'{self.dest}/2026-09/Receipt-02-09-2026-Acme Cloud-49.00 USD.pdf'))
        self.assertTrue(os.path.exists(f'{self.inp}/acme.pdf'))  # originals untouched
        rows = read_csv(f'{self.dest}/summary.csv')
        self.assertEqual(len(rows), 4)

    def test_value_not_in_document_goes_to_review(self):
        recs = self.scan()
        dump({recs['other.pdf']['id']: {'type': 'Invoice', 'date': '2026-10-12', 'vendor': 'Foo Services',
                                        'amount': '1,600.00', 'currency': 'THB'}}, f'{self.work}/manual.json')
        plan = self.plan()
        self.assertEqual(plan['other.pdf']['status'], 'review')
        self.assertIn('amount 1,600.00 not found', plan['other.pdf']['reason'])
        self.assertEqual(plan['slip.png']['status'], 'review')  # never read

    def test_image_readings_must_agree(self):
        recs = self.scan()
        sid = recs['slip.png']['id']
        dump({sid: {'type': 'Slip', 'date': '2026-10-05', 'vendor': 'Shop A', 'amount': '300.00', 'currency': 'THB'}},
             f'{self.work}/manual.json')
        dump({sid: {'date': '2026-10-05', 'amount': '30.00'}}, f'{self.work}/check.json')
        self.assertIn('second reading 30.00', self.plan()['slip.png']['reason'])

    def test_ids_follow_content_not_order(self):
        first = self.scan()['other.pdf']['id']
        make_pdf(f'{self.inp}/aaa.pdf', ['Something else entirely'])  # sorts first, shifts the order
        self.assertEqual(self.scan()['other.pdf']['id'], first)


if __name__ == '__main__':
    unittest.main()
