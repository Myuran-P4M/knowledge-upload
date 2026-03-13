# Architecture Overview — SN Knowledge Upload · Claude

## High-level purpose

Upload local documents to **ServiceNow** via two destination types:

| Destination | Module | Trigger |
|-------------|--------|---------|
| **Knowledge Base article** (`kb_knowledge`) | `sn-kb-upload` / `sn-kb-image` | default |
| **IGT Standard** (`sn_icw_igt_standard`) | `sn-igt-upload` / `sn-igt-skill` | folder name contains "igt" or `--igt` flag |

---

## Project structure

```
SN knowledge upload-Claude/
│
├── upload_all.py            ← Unified CLI dispatcher (main entry point)
├── sn_kb_shared.py          ← Shared utilities: retry, attach, KB/IGT API calls
├── .env                     ← SN credentials + KB config  (gitignored)
│
├── sn-kb-upload/            ── Pipeline 1: Digital documents → KB article
│   ├── upload_to_kb.py
│   ├── requirements.txt
│   ├── README.md
│   └── SKILL.md
│
├── sn-kb-image/             ── Pipeline 2: Photos/scans → KB article (via Claude Vision)
│   ├── image_to_kb.py
│   ├── requirements.txt
│   ├── README.md
│   └── SKILL.md
│
├── sn-igt-upload/           ── Pipeline 3: Procedure docs → IGT Standard + questions
│   ├── igt_to_kb.py
│   ├── .env                 ← IGT reference field sys_ids  (gitignored)
│   ├── requirements.txt
│   ├── README.md
│   └── SKILL.md
│
├── sn-igt-skill/            ── Claude Code skill variant for Pipeline 3
│   ├── extract_steps.py     ← Preview tool: DOCX → JSON (no API calls)
│   ├── SKILL.md
│   └── README.md
│
└── .claude/
    └── commands/
        └── sn-igt-upload.md ← /sn-igt-upload slash command definition
```

---

## Data flow

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                   upload_all.py                         │
                    │                   (dispatcher)                          │
                    └────────────┬────────────────┬────────────────┬──────────┘
                                 │                │                │
                          .pdf   │          .jpg  │        --igt   │  folder contains
                          .docx  │          .png  │       --flag   │  "igt"
                          .xlsx  │          .gif  │        .docx   │  .xlsx
                          .pptx  │          .webp │                │
                                 ▼                ▼                ▼
              ┌──────────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
              │   sn-kb-upload/      │  │  sn-kb-image/   │  │   sn-igt-upload/     │
              │   upload_to_kb.py    │  │  image_to_kb.py │  │   igt_to_kb.py       │
              │                      │  │                 │  │                      │
              │  Local extraction:   │  │  Claude Vision  │  │  python-docx table   │
              │  PyMuPDF, mammoth,   │  │  API (resize,   │  │  parsing: ETAPE |    │
              │  openpyxl, pptx,     │  │  send, parse    │  │  METHODE | PHOTO     │
              │  PIL image compress  │  │  response HTML) │  │  column detection    │
              └──────────┬───────────┘  └────────┬────────┘  └──────────┬───────────┘
                         │                       │                      │
                         └──────────┬────────────┘                      │
                                    │                                   │
                                    ▼                                   ▼
              ┌──────────────────────────────────────┐   ┌───────────────────────────────────┐
              │          sn_kb_shared.py             │   │         sn_kb_shared.py           │
              │                                      │   │                                   │
              │  create_article()                    │   │  create_igt_standard()            │
              │  replace_base64_images()             │   │  get_igt_assessment_template()    │
              │  upload_attachment()                 │   │  create_igt_section()             │
              │  update_article()                    │   │  create_igt_question()            │
              │  retry_on_failure()                  │   │  create_igt_response_option()     │
              └──────────────┬───────────────────────┘   │  update_igt_question()            │
                             │                           │  upload_attachment()              │
                             │                           │  retry_on_failure()               │
                             │                           └──────────────┬────────────────────┘
                             │                                          │
                             ▼                                          ▼
              ┌──────────────────────────────┐      ┌──────────────────────────────────────┐
              │   ServiceNow REST API        │      │   ServiceNow REST API                │
              │   /api/now/table/            │      │   /api/now/table/                    │
              │                              │      │                                      │
              │   kb_knowledge               │      │   sn_icw_igt_standard                │
              │   sys_attachment             │      │   sn_smart_asmt_template  (auto)     │
              └──────────────────────────────┘      │   sn_smart_asmt_section              │
                                                    │   sn_smart_asmt_question             │
                                                    │   sn_smart_asmt_response_option      │
                                                    │   sys_attachment                     │
                                                    └──────────────────────────────────────┘
```

---

## Pipeline 1 — Digital documents → KB article

**Entry:** `upload_all.py` → `sn-kb-upload/upload_to_kb.py`

```
File
 └─ extract_html(file_path)          ← dispatcher
     ├─ extract_pdf()                PyMuPDF — page blocks, table detection,
     │                               column layout, background colour, images
     ├─ extract_docx()               mammoth + style_map (French headings,
     │                               list styles) + PIL image compression
     │                               (900px / q72) + table styling
     ├─ extract_xlsx()               openpyxl → HTML table
     └─ extract_pptx()               python-pptx → slide text blocks
           │
           ▼
     create_article()                POST kb_knowledge (draft)
           │
           ▼
     replace_base64_images()         Upload each data:image/... as attachment,
                                     replace src with /sys_attachment.do URL
           │
           ▼
     update_article()                PATCH kb_knowledge.text with final HTML
```

**DOCX style_map (key mappings):**

| Word style | HTML output |
|------------|-------------|
| `Style1` | `<h2>` |
| `Style2` | `<h1>` |
| `List Paragraph` / `Paragraphedeliste` | `<ul><li>` |
| `TEXTE1` | `<p>` |
| `Header` / `TOC Heading` | `<h2>` |
| `toc 1` | `<p>` |

---

## Pipeline 2 — Photos / scans → KB article (Claude Vision)

**Entry:** `upload_all.py` → `sn-kb-image/image_to_kb.py`

```
Image file
 └─ validate_and_prepare_image()
     ├─ PIL open → EXIF rotation fix
     ├─ Resize to ≤1568px  (Claude Vision API limit) → api_b64
     └─ Keep original at full res for article embed
           │
           ▼
     extract_html_from_image()       Claude Vision API
     Model: claude-sonnet-4-5-20250929 (override via CLAUDE_MODEL)
     Prompt enforces:
       • text accuracy (no hallucination; [illisible] for unreadable)
       • bold only where truly bold
       • tables as <table> not loose text
       • checkboxes as [x]/[ ]
       • HTML only (no markdown, inline styles only)
           │
           ▼
     build_article_html()            Full-res image as base64 + extracted HTML
           │
           ▼
     (same as Pipeline 1: create_article → replace_base64_images → update_article)
```

---

## Pipeline 3 — Procedure docs → IGT Standard + assessment questions

**Entry:** `upload_all.py` → `sn-igt-upload/igt_to_kb.py`

```
DOCX / XLSX file
 └─ extract_steps_from_docx()       python-docx table scan
     ├─ Auto-detect columns by keyword:
     │   ETAPE_KW   → step category column
     │   METHODE_KW → instruction column
     │   PHOTO_KW   → image column
     ├─ Handle merged ETAPE cells (rowspan carry-forward)
     ├─ Deduplicate rows across continuation tables
     └─ Extract images from PHOTO cells via XML/blip
           │
           ▼ list of {title, instructions, order, photos}
     create_igt_standard()
           ├─ short_description  = filename (title-cased)
           ├─ cmdb_assignment_type = SN_ICW_ASSIGNMENT_TYPE
           ├─ owner_group        = SN_IGT_OWNER_GROUP
           ├─ location           = SN_IGT_LOCATION
           ├─ functional_locations = SN_IGT_FUNCTIONAL_LOCATIONS
           └─ category           = SN_IGT_CATEGORY
           │
           ▼ sys_id, number (IGTSXXXXXX)
     get_igt_assessment_template()   GET assessment_template from standard
           │
           ▼ tmpl_sys_id
     For each unique ETAPE value:
       create_igt_section()          sn_smart_asmt_section  (name = ETAPE)
           │
     For each step:
       create_igt_question()         sn_smart_asmt_question
         ├─ label          = METHODE instructions   ← what operator reads
         ├─ section        = section for this ETAPE
         ├─ question_type  = Radio button
         └─ mandatory      = true
               │
         create_igt_response_option() × 2
           ├─ "Fait"     (order 10)
           └─ "Non-fait" (order 20)
               │
         If PHOTO column has images:
           upload_attachment()       → sys_attachment on sn_smart_asmt_question
           update_igt_question()     PATCH guidance_statement with <img> HTML
```

---

## Claude Code skill variant (`/sn-igt-upload`)

```
User types: /sn-igt-upload "IGT docs"
                  │
                  ▼
    .claude/commands/sn-igt-upload.md   ← skill definition (tracked in git)
                  │
        ┌─────────┴──────────────────────────────────────────┐
        │  Claude executes 5 steps using Bash tool:           │
        │                                                      │
        │  1. Verify env vars (both .env files)               │
        │  2. python sn-igt-skill/extract_steps.py <folder>  │
        │     → JSON preview: file / steps / sections / photos│
        │  3. python upload_all.py <folder>                   │
        │  4. Investigate + retry any failures                 │
        │  5. Report with IGTS numbers + ServiceNow URLs      │
        └──────────────────────────────────────────────────────┘
                  │
        sn-igt-skill/extract_steps.py   ← preview tool (no API calls)
          Outputs JSON per file:
            { file, steps, sections, photos, etapes[0..4], step_preview[0..2] }
```

**Difference from Python script:**

| | `python upload_all.py "IGT docs"` | `/sn-igt-upload "IGT docs"` |
|--|-----------------------------------|------------------------------|
| Invocation | Terminal | Claude Code |
| Pre-upload preview | ✗ | ✅ |
| Env validation | Silent fail | ✅ Explicit check |
| Error recovery | Fixed messages | ✅ Claude investigates |
| Result report | Terminal lines | ✅ Formatted + SN URLs |

---

## Shared utilities (`sn_kb_shared.py`)

| Function | Purpose |
|----------|---------|
| `retry_on_failure()` | Exponential backoff (2^n × 2s) on `ConnectionError` / `Timeout`, up to 3 retries |
| `upload_attachment()` | POST `/api/now/attachment/file` — returns `sys_attachment.do?sys_id=…` URL |
| `replace_base64_images()` | Scan HTML for `data:image/…;base64,…`, upload each, rewrite `src` |
| `create_article()` | POST `kb_knowledge` (draft), returns `(sys_id, number)` |
| `update_article()` | PATCH `kb_knowledge.text` with final HTML |
| `create_igt_standard()` | POST `sn_icw_igt_standard` with ref fields from env |
| `get_igt_assessment_template()` | GET `assessment_template.value` from standard record |
| `create_igt_section()` | POST `sn_smart_asmt_section` |
| `create_igt_question()` | POST `sn_smart_asmt_question` (Radio, mandatory) |
| `create_igt_response_option()` | POST `sn_smart_asmt_response_option` ("Fait" / "Non-fait") |
| `update_igt_question()` | PATCH `guidance_statement` with photo HTML |

---

## Environment variables

### Root `.env` — shared by all pipelines

| Variable | Required | Used by |
|----------|----------|---------|
| `SN_INSTANCE` | ✅ | all |
| `SN_USERNAME` | ✅ | all |
| `SN_PASSWORD` | ✅ | all |
| `SN_KB_SYS_ID` | ✅ KB only | KB pipelines |
| `ANTHROPIC_API_KEY` | ✅ images only | Pipeline 2 |
| `CLAUDE_MODEL` | ❌ | Pipeline 2 (default: `claude-sonnet-4-5-20250929`) |

### `sn-igt-upload/.env` — IGT only (overrides root with `override=True`)

| Variable | Maps to SN field |
|----------|------------------|
| `SN_ICW_ASSIGNMENT_TYPE` | `cmdb_assignment_type` |
| `SN_IGT_OWNER_GROUP` | `owner_group` |
| `SN_IGT_LOCATION` | `location` |
| `SN_IGT_FUNCTIONAL_LOCATIONS` | `functional_locations` |
| `SN_IGT_CATEGORY` | `category` |
| `SN_IGT_QUESTION_TYPE` | `question_type` sys_id (optional) |

---

## ServiceNow tables

| Table | Pipeline | Operation |
|-------|----------|-----------|
| `kb_knowledge` | KB (1 & 2) | Create (POST), Update (PATCH) |
| `sys_attachment` | all | Create (POST) |
| `sn_icw_igt_standard` | IGT | Create (POST) |
| `sn_smart_asmt_template` | IGT | Auto-created by SN; Read (GET) |
| `sn_smart_asmt_section` | IGT | Create (POST) |
| `sn_smart_asmt_question` | IGT | Create (POST), Update guidance (PATCH) |
| `sn_smart_asmt_response_option` | IGT | Create (POST) |

---

## Entry points

| Command | What it does |
|---------|-------------|
| `python upload_all.py "folder"` | Route to KB or IGT based on folder name |
| `python upload_all.py "folder" --igt` | Force IGT mode |
| `python sn-kb-upload/upload_to_kb.py "folder"` | KB pipeline standalone |
| `python sn-kb-image/image_to_kb.py "folder"` | Vision pipeline standalone |
| `python sn-igt-upload/igt_to_kb.py "folder"` | IGT pipeline standalone |
| `python sn-igt-skill/extract_steps.py "folder"` | Preview step extraction (no API calls) |
| `/sn-igt-upload "folder"` | Claude Code skill — verify + preview + upload + report |
