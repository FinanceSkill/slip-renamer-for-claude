# Fields and reading rules

Use this whenever you read a slip or receipt into `manual.json` (first reading) or `check.json` (second reading).

## manual.json
```json
{"h3f9a1c2b7d": {"type": "Receipt", "date": "2026-09-02", "vendor": "Acme Cloud", "vendor_full": "Acme Cloud, Inc.",
           "party": "", "amount": "49.00", "currency": "USD", "doc_no": "1234-5678",
           "description": "Pro plan", "bank": "", "notes": ["currency taken as USD from the $ sign"]},
 "h0be47d19a2": {"skip": "not a receipt: a quotation with no payment"}}
```
- Copy values exactly as printed. Leave a field out when the document doesn't print it, and add a note saying so.
- An entry overrides the parser's fields for that file, so you can also use it to correct a parser.
- `skip` sends the file to `_review/` with that reason.

## Fields

| Field | What goes in it |
|---|---|
| `type` | What the document calls itself, in English: Receipt, Invoice, Tax Invoice, Slip (bank transfer), Payslip, Booking |
| `date` | `YYYY-MM-DD` of the payment or transaction: Date paid, Payment date, วันที่ทำรายการ. Use an invoice's own date only when it shows as paid |
| `vendor` | Who received the money, as a short brand name. Drop legal suffixes: Inc., LLC, Co., Ltd., บริษัท … จำกัด. On a transfer slip this is the receiver (ผู้รับ / To) |
| `vendor_full` | The vendor's full name as printed |
| `party` | Who paid, or who it was for: bill-to, customer, passenger, guest. On a transfer slip this is the sender (ผู้โอน / From) |
| `amount` | The total actually paid, as printed: Amount paid, Total paid, ยอดเงิน, จำนวนเงิน, ราคารวม. Never a subtotal, and never a fee shown separately |
| `currency` | An ISO code when one is printed, or an unambiguous symbol: ฿ THB, € EUR, £ GBP, RM MYR, S$ SGD. Read `$` as USD only when no other dollar code is printed, and note it. Keep `¥` as printed, with a note, unless JPY or CNY is printed |
| `doc_no` | The receipt, invoice, booking or transaction reference as printed: เลขที่รายการ, รหัสอ้างอิง, Ref |
| `description` | A few words on what was paid for: product, route, hotel |
| `bank` | On a transfer slip, the sending bank or app |
| `notes` | List of short notes: anything inferred, missing or unusual |

## Thai slips and dates
- **Buddhist-era years**: subtract 543 (2569 → 2026). A two-digit year such as 69 means 2569. Some documents print the CE year with Thai month names, e.g. "29 ก.ย. 2026", so take the year as printed and check that it's plausible.
- **Thai months**: ม.ค. 1, ก.พ. 2, มี.ค. 3, เม.ย. 4, พ.ค. 5, มิ.ย. 6, ก.ค. 7, ส.ค. 8, ก.ย. 9, ต.ค. 10, พ.ย. 11, ธ.ค. 12.
- **Transfer slips** (K PLUS, SCB EASY, Krungthai NEXT, Bualuang, …):
  - Labels to look for: โอนเงินสำเร็จ, จาก / From, ไปยัง / To, จำนวนเงิน, ค่าธรรมเนียม, เลขที่รายการ / รหัสอ้างอิง.
  - A masked account number (xxx-x-x1234-x) is not a document number.
  - A fee is separate from the amount transferred.
- **PDFs that lost characters**: when Thai text comes out broken (e.g. "29 ก ย 2026" or `(cid:6)` artefacts), read through it, and view the rendered page if a figure is unclear.

## check.json (second reading, images only)
`{"<id>": {"date": "YYYY-MM-DD", "amount": "…", "doc_no": "…"}}`

Fill it from the image alone, without looking at the first reading. plan.py compares the two readings. Any difference sends the file to review, so a misread digit never reaches a file name.
