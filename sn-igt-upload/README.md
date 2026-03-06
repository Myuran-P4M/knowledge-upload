# sn-igt-upload — Industrial Guided Task Upload Pipeline

Uploads DOCX/XLSX procedure documents to ServiceNow ICW as **Industrial Guided Task (IGT) Standards**
(`sn_icw_igt_standard`). Each **ETAPE** column value becomes a **section**, each **METHODE**
instruction becomes a **Radio button question**, and images from the **PHOTO** column are attached
as question guidance so operators can follow the procedure step by step.

---

## What it creates (per document)

| SN table | Count | Details |
|----------|-------|---------|
| `sn_icw_igt_standard` | 1 | Short description = filename; reference fields from env |
| `sn_smart_asmt_template` | 1 (auto) | Created automatically by ServiceNow when the Standard is saved |
| `sn_smart_asmt_section` | 1 per unique ETAPE | Name = ETAPE value |
| `sn_smart_asmt_question` | 1 per step | Label = METHODE instruction; type = Radio button; mandatory |
| `sn_smart_asmt_response_option` | 2 per question | **"Fait"** (order 10) and **"Non-fait"** (order 20) |
| Attachments on question | 1+ per step | Images from the PHOTO column, set as `guidance_statement` |

---

## Supported source files

| Extension | Step detection |
|-----------|---------------|
| `.docx`   | python-docx table scan — ETAPE \| METHODE \| PHOTO column auto-detection |
| `.xlsx`   | openpyxl row scan — same column keywords |

---

## Column auto-detection (DOCX & XLSX)

The pipeline searches each table's header row for these keyword groups:

| Column role | Keywords (case-insensitive) |
|-------------|----------------------------|
| **ETAPE** (section)  | `etape`, `étape`, `step`, `tâche`, `task`, `operation`, `opération` |
| **METHODE** (question label) | `method`, `méthode`, `instruction`, `description`, `procédure`, `procedure` |
| **PHOTO** (guidance images) | `photo`, `image`, `picture`, `illustration`, `figure`, `img` |

Tables without an ETAPE **or** METHODE column are skipped.
Merged ETAPE cells (rowspan) are carried forward to subsequent rows.
Duplicate rows (same ETAPE + METHODE prefix) are skipped across continuation tables.

---

## Environment variables

Two `.env` files are loaded:

### `<project-root>/.env` — credentials (shared by all pipelines)

| Variable | Required | Description |
|----------|----------|-------------|
| `SN_INSTANCE` | ✅ | `https://your-instance.service-now.com` |
| `SN_USERNAME` | ✅ | ServiceNow username |
| `SN_PASSWORD` | ✅ | ServiceNow password |

> `SN_KB_SYS_ID` is **not** needed — IGT Standards are independent of the Knowledge Base.

### `sn-igt-upload/.env` — IGT reference fields (overrides shared)

| Variable | Maps to SN field |
|----------|-----------------|
| `SN_ICW_ASSIGNMENT_TYPE` | `cmdb_assignment_type` |
| `SN_IGT_OWNER_GROUP` | `owner_group` |
| `SN_IGT_LOCATION` | `location` |
| `SN_IGT_FUNCTIONAL_LOCATIONS` | `functional_locations` |
| `SN_IGT_CATEGORY` | `category` |
| `SN_IGT_QUESTION_TYPE` | Question type sys_id (optional; default = Radio button) |

All reference field variables accept a **sys_id** string. Any variable that is empty or missing is
simply omitted from the POST payload (no error).

---

## Setup

```bash
pip install -r requirements.txt
```

Create / update `.env` (project root):
```
SN_INSTANCE=https://your-instance.service-now.com
SN_USERNAME=admin
SN_PASSWORD=yourpassword
```

Create `sn-igt-upload/.env` with IGT reference sys_ids:
```
SN_ICW_ASSIGNMENT_TYPE=functional_location
SN_IGT_OWNER_GROUP=<sys_id>
SN_IGT_LOCATION=<sys_id>
SN_IGT_FUNCTIONAL_LOCATIONS=<sys_id>
SN_IGT_CATEGORY=<sys_id>
```

---

## Usage

### Standalone
```bash
python sn-igt-upload/igt_to_kb.py "IGT docs"
```

### Via unified dispatcher (recommended)
```bash
# Auto-triggered when folder name contains "igt"
python upload_all.py "IGT docs"

# Force IGT mode on any folder name
python upload_all.py "my_procedures" --igt
```

### As a Claude Code skill (with preview + error recovery + formatted report)
```
/sn-igt-upload "IGT docs"
```

---

## IGT Standard fields populated

| SN field | Source |
|----------|--------|
| `short_description` | Filename (title-cased, extension removed) |
| `state` | `1` (draft) |
| `active` | `true` |
| `cmdb_assignment_type` | `SN_ICW_ASSIGNMENT_TYPE` env var |
| `owner_group` | `SN_IGT_OWNER_GROUP` env var |
| `location` | `SN_IGT_LOCATION` env var |
| `functional_locations` | `SN_IGT_FUNCTIONAL_LOCATIONS` env var |
| `category` | `SN_IGT_CATEGORY` env var |

---

## Section fields (sn_smart_asmt_section)

| SN field | Source |
|----------|--------|
| `assessment_template` | Auto-created template linked to the IGT Standard |
| `name` | ETAPE column value |
| `order` | Incremented per unique ETAPE encountered |

One section is created per **unique ETAPE value**. Steps sharing the same ETAPE reuse the same section.

---

## Question fields (sn_smart_asmt_question)

| SN field | Source |
|----------|--------|
| `assessment_template` | Linked template sys_id |
| `section` | Section for this step's ETAPE |
| `label` | METHODE instruction text (what the operator reads and acts on) |
| `guidance_statement` | `<img>` HTML of PHOTO column images (set after upload) |
| `order` | Row order within the document |
| `mandatory` | `true` |
| `question_type` | Radio button (`SN_IGT_QUESTION_TYPE` or built-in default) |

---

## Response options (sn_smart_asmt_response_option)

Two choices are created for every question:

| `text_label` | `order` |
|--------------|---------|
| Fait         | 10 |
| Non-fait     | 20 |

---

## Expected terminal output (per file)

```
[igt] my_procedure.docx
  Found 107 step(s), 95 photo(s)
  Creating IGT Standard... OK (IGTS0001234)
  Creating 107 question(s)... 107 OK
  Sections created: 51
```
