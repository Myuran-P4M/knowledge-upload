#!/usr/bin/env python3
"""IGT Skill — Step extraction preview tool.

Scans a folder (or single DOCX file) for procedure tables and outputs a JSON
summary to stdout.  Used by the /sn-igt-upload Claude Code skill to preview
what will be uploaded before any ServiceNow API calls are made.

Usage:
    python sn-igt-skill/extract_steps.py "IGT docs"
    python sn-igt-skill/extract_steps.py "IGT docs/my_procedure.docx"

Output (JSON array, one entry per file):
    [
      {
        "file": "my_procedure.docx",
        "steps": 107,
        "sections": 51,
        "photos": 95,
        "etapes": ["Désinfection", "Pupitre Soutireuse", ...],   ← first 5
        "step_preview": [                                          ← first 3 steps
          {"order": 1, "title": "Désinfection",
           "instructions": "Désinfecter à l'éthanol...", "has_photo": true},
          ...
        ]
      }
    ]
"""

import sys
import json
from pathlib import Path

# ── Column keyword sets ────────────────────────────────────────────────────────

_ETAPE_KW   = ("etape", "étape", "section", "step", "tâche", "operation", "opération")
_METHODE_KW = ("method", "méthode", "instruction", "description", "procédure", "procedure", "action", "task", "tâche")
_PHOTO_KW   = ("photo", "image", "picture", "illustration", "figure", "img", "guidance", "reference")


def _col_index(headers, *keywords):
    for i, h in enumerate(headers):
        if any(kw in h.strip().lower() for kw in keywords):
            return i
    return -1


def _has_image(cell, doc):
    """Return True if the table cell contains at least one embedded image."""
    try:
        from docx.oxml.ns import qn
        for blip in cell._element.iter(qn("a:blip")):
            if blip.get(qn("r:embed")):
                return True
    except Exception:
        pass
    return False


def extract_steps_from_docx(file_path):
    """Return a list of step dicts from a DOCX procedure file."""
    from docx import Document

    doc    = Document(file_path)
    steps  = []
    order  = 0
    seen   = set()

    for table in doc.tables:
        if not table.rows:
            continue

        headers = [cell.text.strip() for cell in table.rows[0].cells]
        ec = _col_index(headers, *_ETAPE_KW)
        mc = _col_index(headers, *_METHODE_KW)
        pc = _col_index(headers, *_PHOTO_KW)

        if ec == -1 and mc == -1:
            continue

        prev = ""
        for row in table.rows[1:]:
            cells = row.cells
            e = cells[ec].text.strip() if 0 <= ec < len(cells) else ""
            m = cells[mc].text.strip() if 0 <= mc < len(cells) else ""

            e = e or prev
            if e:
                prev = e
            if not (e or m):
                continue

            key = (e[:80], m[:80])
            if key in seen:
                continue
            seen.add(key)

            order += 1
            has_p = _has_image(cells[pc], doc) if 0 <= pc < len(cells) else False
            steps.append({
                "order":        order,
                "title":        e[:255],
                "instructions": m[:400],
                "has_photo":    has_p,
            })

    return steps


def summarise(file_path):
    """Return a summary dict for one DOCX file, or an error dict."""
    try:
        steps  = extract_steps_from_docx(file_path)
        etapes = list(dict.fromkeys(s["title"] for s in steps if s["title"]))
        photos = sum(1 for s in steps if s["has_photo"])
        return {
            "file":         file_path.name,
            "steps":        len(steps),
            "sections":     len(etapes),
            "photos":       photos,
            "etapes":       etapes[:5],
            "step_preview": steps[:3],
        }
    except Exception as exc:
        return {"file": file_path.name, "error": str(exc)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python sn-igt-skill/extract_steps.py <folder_or_docx>",
              file=sys.stderr)
        sys.exit(1)

    target = Path(sys.argv[1])

    if target.is_dir():
        files = sorted(f for f in target.iterdir()
                       if f.is_file() and f.suffix.lower() == ".docx")
    elif target.is_file() and target.suffix.lower() == ".docx":
        files = [target]
    else:
        print(f"ERROR: '{target}' is not a folder or a .docx file.", file=sys.stderr)
        sys.exit(1)

    if not files:
        print(json.dumps([], indent=2))
        return

    result = [summarise(f) for f in files]
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
