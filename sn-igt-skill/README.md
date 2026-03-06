# sn-igt-skill — Claude Code Skill Variant

This folder is the **Claude Code skill** interface for uploading procedure
documents to ServiceNow ICW as Industrial Guided Task (IGT) Standards.

The skill is defined as a slash command in `.claude/commands/sn-igt-upload.md`
and is invoked directly from Claude Code — no terminal, no Python command needed.

---

## Quick start

In Claude Code, type:

```
/sn-igt-upload "IGT docs"
```

Claude will:
1. Verify your environment variables
2. Preview the step extraction (files, section count, question count, photos)
3. Run the upload pipeline
4. Report results with direct ServiceNow links

---

## How it differs from the Python script variant

| | `sn-igt-upload/` (Python) | `sn-igt-skill/` (Claude skill) |
|--|---------------------------|--------------------------------|
| **Invocation** | `python upload_all.py "IGT docs"` | `/sn-igt-upload "IGT docs"` |
| **Preview** | No | Yes — shows step counts before uploading |
| **Error handling** | Static messages | Claude investigates, retries, explains |
| **Result report** | Terminal output | Formatted table with SN URLs |
| **Env check** | Silent failures | Explicit check, stops early if misconfigured |

Both variants use the same underlying pipeline (`upload_all.py` → `igt_to_kb.py`
→ `sn_kb_shared.py`).

---

## Folder contents

| File | Purpose |
|------|---------|
| `extract_steps.py` | Standalone preview tool — extracts steps to JSON without uploading |
| `SKILL.md` | Claude Code skill metadata |
| `README.md` | This file |

The slash command itself lives at `.claude/commands/sn-igt-upload.md`.

---

## extract_steps.py — Preview tool

Run before uploading to see exactly what will be created:

```bash
python sn-igt-skill/extract_steps.py "IGT docs"
```

Example output:

```json
[
  {
    "file": "EV- CONDUITE-CHANGEMENT DE FORMAT - COMBI - Ligne 2.docx",
    "steps": 107,
    "sections": 51,
    "photos": 95,
    "etapes": ["Désinfection", "Pupitre Soutireuse", "Démarrage Alimentation Bouchon", ...],
    "step_preview": [
      {"order": 1, "title": "Désinfection",
       "instructions": "Désinfecter à l'éthanol : Les étoiles de la rinceuse...",
       "has_photo": true},
      ...
    ]
  }
]
```

---

## Prerequisites

- `.env` (project root) — SN credentials
- `sn-igt-upload/.env` — IGT reference fields
- `pip install python-docx python-dotenv` (already in `sn-igt-upload/requirements.txt`)
