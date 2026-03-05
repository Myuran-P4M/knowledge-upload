# sn-igt-upload — Industrial Guided Task Upload Pipeline

Uploads documents to ServiceNow ICW module as **Industrial Guided Task (IGT) Standards**
(`sn_icw_igt_standard` table). Steps inside procedure documents are created as individual
`sn_icw_std_task` records linked to the standard.

## What it creates

| Source | SN record created |
|--------|-------------------|
| One document | One `sn_icw_igt_standard` + N `sn_icw_igt_task` steps |
| Image attached | Attachment on the IGT Standard record |

## Supported source files

| Extension | Extraction method | Step detection |
|-----------|-------------------|---------------|
| `.docx`   | mammoth (HTML) + python-docx | ETAPE \| METHODE table rows |
| `.pdf`    | PyMuPDF (text, tables, images) | — |
| `.xlsx`   | openpyxl | Each data row = one step |
| `.pptx`   | python-pptx (slide text) | — |
| `.png/.jpg/.jpeg` | Base64 embed | — |

## Step column auto-detection

**DOCX**: looks for a table whose first row contains any of:
- `ETAPE` / `Étape` / `Step` / `Task` / `Opération` → step title column
- `MÉTHODE` / `Method` / `Instructions` / `Description` → instructions column

**Excel**: header row keywords:
- Title: `Step`, `Étape`, `Name`, `Task`
- Instructions: `Instructions`, `Method`, `Méthode`, `Description`
- Notes (optional): `Notes`, `Remarks`, `Remarques`

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SN_INSTANCE` | ✅ | — | `https://your-instance.service-now.com` |
| `SN_USERNAME` | ✅ | — | ServiceNow admin username |
| `SN_PASSWORD` | ✅ | — | ServiceNow admin password |
| `SN_ICW_ASSIGNMENT_TYPE` | ❌ | `equipment` | `cmdb_assignment_type` value for new IGT Standards |

> `SN_KB_SYS_ID` is **not** required — IGT Standards are not in the Knowledge Base.

## Setup

```bash
pip install -r requirements.txt
```

Add to your `.env`:
```
SN_INSTANCE=https://your-instance.service-now.com
SN_USERNAME=admin
SN_PASSWORD=yourpassword
SN_ICW_ASSIGNMENT_TYPE=equipment
```

## Usage

### Standalone
```bash
python sn-igt-upload/igt_to_kb.py "IGT docs"
```

### Via unified dispatcher (recommended)
```bash
# Auto-triggered when folder name contains "igt"
python upload_all.py "IGT docs"

# Or force IGT mode on any folder
python upload_all.py "my_procedures" --igt
```

### As a Claude Code skill
```
/sn-igt-upload IGT docs
```

## IGT Standard fields populated

| SN field | Source |
|----------|--------|
| `short_description` | Filename (title-cased) |
| `detailed_description` | Full extracted HTML |
| `state` | `1` (draft) |
| `active` | `true` |
| `cmdb_assignment_type` | `SN_ICW_ASSIGNMENT_TYPE` env var |

## Step fields populated (sn_icw_igt_task)

| SN field | Source |
|----------|--------|
| `standard` | Parent IGT Standard `sys_id` |
| `short_description` | ETAPE / Step column value |
| `description` | METHODE / Instructions column value |
| `order` | Row index |

> The step table is `sn_icw_igt_task` (child class of `sn_icw_std_task`).
> Field names `description` and `order` are inherited from the task base class.
