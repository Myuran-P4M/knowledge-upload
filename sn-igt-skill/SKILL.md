---
name: sn-igt-upload
description: >
  Upload DOCX/XLSX procedure documents to ServiceNow ICW as Industrial Guided
  Task (IGT) Standards.  Each ETAPE becomes a section; each METHODE instruction
  becomes a Radio button question with "Fait" and "Non-fait" answer choices.
  PHOTO column images are attached to their questions as guidance.
command: /sn-igt-upload
arguments: "<folder_path>"
version: 2.0.0
variant: claude-skill   # Claude Code slash command — see .claude/commands/sn-igt-upload.md
---

## Invocation

```
/sn-igt-upload "IGT docs"
/sn-igt-upload "C:/path/to/procedures"
```

## Records created per document

| SN table | Count | Field mapping |
|----------|-------|---------------|
| `sn_icw_igt_standard` | 1 | short_description = filename |
| `sn_smart_asmt_section` | 1 per ETAPE | name = ETAPE value |
| `sn_smart_asmt_question` | 1 per step | label = METHODE instruction |
| `sn_smart_asmt_response_option` | 2 per question | "Fait" / "Non-fait" |
| Attachments on question | 1+ per step | PHOTO column images |

## Configuration files

| File | Purpose |
|------|---------|
| `.env` | SN credentials (`SN_INSTANCE`, `SN_USERNAME`, `SN_PASSWORD`) |
| `sn-igt-upload/.env` | IGT references (`SN_IGT_OWNER_GROUP`, `SN_IGT_LOCATION`, etc.) |

## Helper tools in this folder

| Script | Usage |
|--------|-------|
| `extract_steps.py` | Preview step extraction without uploading — outputs JSON |

## Allowed tools (Claude Code)

- Bash: `python *`
- Bash: `pip *`
- Read
- Glob
