# Slip Renamer for Claude

A [Claude Code](https://claude.com/claude-code) skill (also packaged as a plugin) that renames financial slips and receipts by their content. It handles bank transfer slips, e-receipts, invoices, booking receipts and payslips, as PDFs or images, in Thai or English. Each file is copied to a new folder under a name built from its own date, vendor, amount and document number, in the format you pick. The copies are sorted into month folders, and a summary CSV lists them all.

> **ภาษาไทย:** สกิลสำหรับ Claude Code ที่เปลี่ยนชื่อสลิปและใบเสร็จตามเนื้อหาในไฟล์ (สลิปโอนเงิน, e-receipt, ใบแจ้งหนี้, ใบเสร็จการจอง, payslip ทั้ง PDF และรูปภาพ)
> - คัดลอกไปโฟลเดอร์ใหม่ แยกตามเดือน พร้อมไฟล์สรุป CSV ไฟล์ต้นฉบับไม่ถูกแตะ
> - ถามรูปแบบชื่อไฟล์ทุกครั้ง โดยเสนอตัวเลือกพร้อมตัวอย่างจากไฟล์จริงของคุณ
> - ห้ามแต่งข้อมูล: วันที่ ยอดเงิน และเลขเอกสารในชื่อต้องพิมพ์อยู่ในไฟล์จริง ไม่อย่างนั้นไฟล์จะไปอยู่ใน `_review/`

## Example

```
E-receipt (3).pdf             ->  2026-09/Receipt-14-09-2026-Trip.com-4,250.00 THB.pdf
Receipt-1234-5678.pdf         ->  2026-09/Receipt-02-09-2026-Acme Cloud-49.00 USD.pdf
IMG_0412.png (transfer slip)  ->  2026-10/Slip-05-10-2026-Shop A-300.00 THB.png
```

## How it works

Most receipts are digital PDFs that carry their own text, so reading them as images wastes tokens and risks misread digits. The skill splits the work by cost:

| Step | Done by | On a sample of 200 real receipts |
|---|---|---|
| File type, duplicates, text extraction | script | a few seconds in total; 7 exact duplicates found |
| Known layouts (Stripe-style receipts, Trip.com flight and hotel, Thai and English) | parsers | 182 files (91%) named with no model reading |
| Everything else | Claude reads the **text**; it views the **image** only when there is no text | 18 files |
| Checks | script | every date, amount and document number in a name must be printed in the file |

- **Images** (e.g. slips from a banking app) have no text to check against. They need two independent readings, the second by an Opus agent, and the two readings must agree.
- **Unnamed files**: a file whose chosen name needs a value the document doesn't print goes to `_review/` under its original name.
- **Originals** are never moved or changed.

## Requirements

- Claude Code. Subagents (the Agent tool) are used only for image slips and for large batches.
- Python 3.9+ with `pdfplumber`:
  ```bash
  pip install -r requirements.txt
  ```

## Install

**As a plugin.** In Claude Code:

```
/plugin marketplace add FinanceSkill/slip-renamer-for-claude
/plugin install slip-renamer@slip-renamer-for-claude
```

**As a personal skill:**

```bash
git clone https://github.com/FinanceSkill/slip-renamer-for-claude.git
ln -s "$PWD/slip-renamer-for-claude/skills/slip-renamer" ~/.claude/skills/slip-renamer
```

## Use

```
/slip-renamer ~/Downloads/receipts/
```

You can also ask in plain words, e.g. "เปลี่ยนชื่อใบเสร็จในโฟลเดอร์นี้ตามวันที่และยอดเงิน". The skill then:

1. Scans the files and reads only what the parsers missed.
2. Shows naming options rendered on your own files, with how many files each option can name and how many names would clash. If it sees names you already use, it offers that convention first.
3. Asks you to choose the format, whether to use month folders, and where to put the copies.
4. Checks every name, copies the files, and writes `summary.csv`.

### Template placeholders

`{type}` `{DD}` `{MM}` `{YYYY}` `{YY}` `{date}` `{vendor}` `{vendor_full}` `{party}` `{amount}` `{amount_plain}` `{currency}` `{doc_no}` `{description}` `{bank}`

For example, `{type}-{DD}-{MM}-{YYYY}-{vendor}-{amount} {currency}` gives `Receipt-02-09-2026-Acme Cloud-49.00 USD.pdf`.

## Files

```
.claude-plugin/
  plugin.json             plugin manifest
  marketplace.json        lets `/plugin marketplace add` install straight from this repo
skills/slip-renamer/
  SKILL.md                the workflow: scan, read, ask the format, plan and check, copy, report
  references/fields.md    field definitions and reading rules (Thai dates and months, transfer slips)
  scripts/scan.py         real file type, content hash, text layer, layout parsing
  scripts/parsers.py      layout parsers; add one when a new layout shows up in many files
  scripts/plan.py         naming options (--suggest), template rendering, checks, collision handling
  scripts/apply.py        copy to the new names, _review/ folder, summary.csv
tests/test_scripts.py     tests on synthetic documents
```

## Development

```bash
python3 -m unittest discover tests
```

The tests build their own small PDFs and images. Real receipts never belong in this repository.

## Privacy

During a session, Claude reads the contents of the slips and receipts, the same as any file you open in Claude Code. The summary CSV lists amounts, vendors and document numbers. Keep receipts and outputs out of this repository: the included `.gitignore` excludes PDFs, images, CSVs and JSON work files.

## License

MIT. See [LICENSE](LICENSE).
