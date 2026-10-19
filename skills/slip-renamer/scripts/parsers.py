"""Layout parsers: pull naming fields out of a document's text layer.

Each parser takes the full text and returns (layout, fields, notes) or None when the layout doesn't match.
Fields are copied from the text; a field the parser can't find is left out, so the record goes to a
reader instead of getting a guess.
"""
import re
from datetime import date

MONTHS = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
     'November', 'December'], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS['sept'] = 9
TH_MONTHS = {m: i for i, m in enumerate(['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.',
                                          'ต.ค.', 'พ.ย.', 'ธ.ค.'], 1)}
SYMBOLS = {'฿': 'THB', '€': 'EUR', '£': 'GBP', '₩': 'KRW', '₹': 'INR', 'A$': 'AUD', 'S$': 'SGD', 'HK$': 'HKD',
           'CA$': 'CAD', 'NZ$': 'NZD', 'R$': 'BRL', 'RM': 'MYR', 'US$': 'USD'}
CODES = ('THB|USD|EUR|GBP|JPY|CNY|SGD|MYR|HKD|AUD|CAD|NZD|KRW|INR|VND|IDR|PHP|AED|CHF|TWD|BRL|MXN|PLN|CZK|HUF|SEK|NOK|'
         'DKK|ZAR|TRY|SAR|QAR|KWD|BHD|OMR|ILS|EGP|KZT|RUB|UAH|RON|BGN|LAK|KHR|MMK|BDT|PKR|LKR|NPR|MOP|CLP|COP|PEN|ARS')
LEGAL = re.compile(r'(,?\s+(Inc\.?|Incorporated|LLC|L\.L\.C\.|PBC|OpCo|Corp\.?|Corporation|Co\.,? Ltd\.?|Ltd\.?|'
                   r'Limited|Pte\.? Ltd\.?|PTE\.? LTD\.?|Pty\.? Ltd\.?|S\.L\.U\.|S\.L\.|GmbH|B\.V\.|SAS|S\.A\.|AG))+\s*$', re.I)


def en_date(s):
    """'September 2, 2026' / 'Sep 2, 2026' / '2 Sep 2026' -> '2026-09-02'."""
    m = re.search(r'([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})', s)
    if m and m.group(1).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2))).isoformat()
    m = re.search(r'(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})', s)
    if m and m.group(2).lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1))).isoformat()
    return None


def th_date(s):
    """'18 ส.ค. 2026' or '11 ส.ค. 2569' (Buddhist era) -> ISO."""
    m = re.search(r'(\d{1,2})\s*(' + '|'.join(map(re.escape, TH_MONTHS)) + r')\s*(\d{4})', s)
    if not m:
        return None
    y = int(m.group(3))
    return date(y - 543 if y > 2400 else y, TH_MONTHS[m.group(2)], int(m.group(1))).isoformat()


def money(token_cur, token_amt, text):
    """Currency code from a printed symbol or code; '$' and '¥' are ambiguous, so look for a code in the text."""
    cur, notes = token_cur.strip(), []
    if re.fullmatch(CODES, cur):
        return cur, token_amt, notes
    if cur in SYMBOLS:
        return SYMBOLS[cur], token_amt, notes
    if cur == '$':
        codes = set(re.findall(r'\b(USD|AUD|SGD|CAD|NZD|HKD)\b', text))
        if len(codes) == 1:
            return codes.pop(), token_amt, notes
        return 'USD', token_amt, ['currency taken as USD from the $ sign']
    if cur == '¥':
        codes = set(re.findall(r'\b(JPY|CNY|RMB)\b', text))
        if len(codes) == 1:
            return codes.pop().replace('RMB', 'CNY'), token_amt, notes
        return None, token_amt, ['¥ amount: JPY or CNY not stated']
    return None, token_amt, [f'unknown currency {cur!r}']


def short_vendor(name):
    name = re.sub(r'\(?@[\w.-]+\)?', '', name).strip(' ,')
    short = LEGAL.sub('', name).strip(' ,')
    return short or name


def stripe_receipt(text):
    """Stripe-hosted receipts (most SaaS vendors billing through Stripe): 'Receipt number', '$X paid on <date>'."""
    m = re.search(r'Receipt number\s+([\d][\d ]*\d)', text)
    if not m:
        return None
    f, notes = {'type': 'Receipt', 'doc_no': m.group(1).replace(' ', '-')}, []
    d = re.search(r'Date paid\s+(.+)', text)
    if d and en_date(d.group(1)):
        f['date'] = en_date(d.group(1))
    sym = r'(A\$|S\$|HK\$|CA\$|NZ\$|US\$|R\$|[$฿€£¥₩₹])\s?([\d,]+(?:\.\d+)?)'
    p = (re.search(r'^\s*' + sym + r' paid (?:on|as of) ', text, re.M)
         or re.search(r'Amount paid\s+' + sym, text) or re.search(r'^Total\s+' + sym + r'\s*$', text, re.M))
    if p:
        cur, amt, n = money(p.group(1), p.group(2), text)
        notes += n
        if cur:
            f['currency'] = cur
        f['amount'] = amt
    b = re.search(r'^(.*?)\s*Bill to', text, re.M)
    if b and b.group(1).strip():
        f['vendor_full'] = re.sub(r'\(?@[\w.-]+\)?', '', b.group(1)).strip(' ,')
        f['vendor'] = short_vendor(b.group(1))
    return 'stripe-receipt', f, notes


def _tripcom_total(text, prefer):
    for label in prefer:
        for line in text.splitlines():
            if not line.startswith(label):
                continue
            m = re.search(rf'(?:\b({CODES})|(A\$|S\$|HK\$|US\$|[$฿€£¥]))\s?([\d,]+(?:\.\d+)?)\s*$', line)
            if m:
                return m.group(1) or m.group(2), m.group(3)
    return None, None


def _flight_route(text):
    """First segment's route. A long city name wraps: its tail sits on the line after the route, before the
    airline and flight-number lines, so 2 lines before the flight number mean the first one is the tail."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r'(.+? - .+?) [A-Z][a-z]+ \d{1,2}, \d{4} .*class$', line)
        if not m:
            continue
        route = m.group(1).strip()
        for j in range(i + 1, min(i + 5, len(lines))):
            if re.fullmatch(r'[A-Z0-9]{2}\s?\d{1,4}[A-Z]?', lines[j].strip()):
                if j - i == 3:
                    route += ' ' + lines[i + 1].strip()
                break
        return route
    return None


def tripcom_th_hotel(text):
    """Thai-language Trip.com hotel receipt. Its Thai text comes out broken (split vowels, (cid:N)), so match
    on the parts that survive: หมายเลขการจอง, the payment-date line with "(UTC", and the paid-total line
    that carries the card in brackets."""
    f, notes = {'type': 'Receipt', 'vendor': 'Trip.com', 'vendor_full': 'Trip.com Travel Singapore Pte. Ltd.'}, []
    f['doc_no'] = re.search(r'หมายเลขการจอง:\s*(\d+)', text).group(1)
    for line in text.splitlines():
        if '(UTC' in line and th_date(line):
            f['date'] = th_date(line)
            break
    amounts = [(l, re.search(rf'-?\b({CODES})\s?([\d,]+(?:\.\d+)?)\s*$', l)) for l in text.splitlines()]
    amounts = [(l, m) for l, m in amounts if m and not re.search(r'-\s*[A-Z]{3}', l)]
    paid = [x for x in amounts if '(' in x[0]] or amounts[:1]
    if paid:
        code, amt, n = money(paid[0][1].group(1), paid[0][1].group(2), text)
        f.update(currency=code, amount=amt)
        notes += n
    h = re.search(r'^โรงแรม (.+)$', text, re.M)
    if h:
        f['description'] = 'Hotel ' + h.group(1).strip()
    return 'tripcom-hotel-th', f, notes


def tripcom(text):
    """Trip.com flight and hotel receipts."""
    if not re.search(r'(?i)trip\.com', text):
        return None
    if not re.search(r'Booking No\.\s*\d+', text):
        return tripcom_th_hotel(text) if re.search(r'หมายเลขการจอง:\s*\d+', text) and re.search(r'^โรงแรม ', text, re.M) else None
    f, notes = {'type': 'Receipt', 'vendor': 'Trip.com', 'vendor_full': 'Trip.com Travel Singapore Pte. Ltd.'}, []
    f['doc_no'] = re.search(r'Booking No\.\s*(\d+)', text).group(1)
    if re.search(r'Check-in date', text):
        layout = 'tripcom-hotel'
        d = re.search(r'Payment date\s+(.+)', text)
        cur, amt = _tripcom_total(text, ['Total paid', 'Total amount'])
        h = re.search(r'^Hotel (.+)$', text, re.M)
        if h:
            f['description'] = 'Hotel ' + h.group(1).strip()
        g = re.search(r'^Guest names\s+(.+)$', text, re.M)
        if g:
            f['party'] = g.group(1).strip()
    else:
        layout = 'tripcom-flight'
        d = re.search(r'Date of Booking:.*?,\s*([A-Za-z]+ \d{1,2}, \d{4})', text)
        cur, amt = _tripcom_total(text, ['Total paid', 'Total'])
        route = _flight_route(text)
        if route:
            f['description'] = 'Flight ' + route
        c = re.search(r'^Contact Name\s+(.+)$', text, re.M)
        if c:
            f['party'] = c.group(1).strip()
    if d and en_date(d.group(1)):
        f['date'] = en_date(d.group(1))
    if amt:
        code, amt, n = money(cur, amt, text)
        notes += n
        f['amount'] = amt
        if code:
            f['currency'] = code
    return layout, f, notes


PARSERS = [stripe_receipt, tripcom]
REQUIRED = ('date', 'vendor', 'amount', 'currency')


def parse(text):
    """Return (layout, fields, notes); layout None when no parser matched."""
    for p in PARSERS:
        r = p(text)
        if r:
            return r
    return None, {}, []
