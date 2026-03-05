"""Industrial Guided Task (IGT) upload pipeline — ServiceNow ICW module.

Reads source documents and creates IGT Standard records in ServiceNow:
  table: sn_icw_igt_standard  (extends sn_icw_std_standard)
  steps: sn_icw_std_task       (one record per procedure step)

Supported source files
  .docx   — full HTML via mammoth + procedure table rows extracted as steps
             (detects ETAPE | METHODE | PHOTO column layout automatically)
  .pdf    — full HTML via PyMuPDF (text, tables, images)
  .xlsx   — header row auto-detected; each data row becomes one IGT step
             expected columns: Step/Étape | Instructions/Méthode | Notes
  .pptx   — slide text blocks as IGT description
  .png/.jpg/.jpeg — attached as reference images to the IGT Standard

Triggered automatically by upload_all.py when:
  - the source folder name contains "igt" (case-insensitive), OR
  - the --igt flag is passed on the command line

Environment variables (same .env as KB pipelines, plus):
  SN_ICW_ASSIGNMENT_TYPE  — cmdb_assignment_type value for new standards
                            (default: "equipment")
"""

import os
import sys
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

_script_dir = Path(__file__).parent
load_dotenv(_script_dir.parent / ".env")

# Allow imports from sibling sn-kb-upload and parent
sys.path.insert(0, str(_script_dir.parent))
sys.path.insert(0, str(_script_dir.parent / "sn-kb-upload"))

from sn_kb_shared import (
    replace_base64_images,
    create_igt_standard,
    update_igt_standard,
    create_igt_step,
)
import upload_to_kb  # reuse all extraction functions


# ── Constants ─────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx", ".png", ".jpg", ".jpeg"}

# Column keywords used when auto-detecting procedure table headers
_ETAPE_KW    = ("etape", "étape", "step", "tâche", "task", "operation", "opération")
_METHODE_KW  = ("method", "méthode", "instruction", "description", "procédure", "procedure")


# ── Config ────────────────────────────────────────────────────────────────────

def get_config():
    """Read and validate required environment variables."""
    instance      = os.environ.get("SN_INSTANCE", "").rstrip("/")
    username      = os.environ.get("SN_USERNAME", "")
    password      = os.environ.get("SN_PASSWORD", "")
    assign_type   = os.environ.get("SN_ICW_ASSIGNMENT_TYPE", "equipment")

    missing = []
    if not instance: missing.append("SN_INSTANCE")
    if not username: missing.append("SN_USERNAME")
    if not password: missing.append("SN_PASSWORD")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    return instance, username, password, assign_type


# ── Step extraction ────────────────────────────────────────────────────────────

def _col_index(headers, *keywords):
    """Return the first column index whose lowercased header contains any keyword."""
    for i, h in enumerate(headers):
        hl = h.strip().lower()
        if any(kw in hl for kw in keywords):
            return i
    return -1


def extract_steps_from_docx(file_path):
    """Parse ETAPE | METHODE procedure tables from a DOCX file.

    Returns a list of dicts: {title, instructions, order}.
    Handles merged/rowspan ETAPE cells by carrying the last non-empty title forward.
    Skips tables that do not have recognisable step/method columns.
    """
    try:
        from docx import Document
    except ImportError:
        print("  Warning: python-docx not installed — step extraction skipped")
        return []

    try:
        doc = Document(file_path)
    except Exception as e:
        print(f"  Warning: could not open DOCX for step extraction: {e}")
        return []

    steps = []
    order = 0
    seen = set()   # deduplicate rows shared across continuation tables

    for table in doc.tables:
        if not table.rows:
            continue

        # Auto-detect column positions from the first row
        header_texts = [cell.text.strip() for cell in table.rows[0].cells]
        etape_col   = _col_index(header_texts, *_ETAPE_KW)
        methode_col = _col_index(header_texts, *_METHODE_KW)

        if etape_col == -1 and methode_col == -1:
            continue  # not a procedure table

        prev_etape = ""
        for row in table.rows[1:]:
            cells = row.cells
            etape   = cells[etape_col].text.strip()   if 0 <= etape_col   < len(cells) else ""
            methode = cells[methode_col].text.strip() if 0 <= methode_col < len(cells) else ""

            # Carry forward ETAPE when the cell is merged (rowspan)
            if not etape:
                etape = prev_etape
            else:
                prev_etape = etape

            if not (etape or methode):
                continue

            key = (etape[:80], methode[:80])
            if key in seen:
                continue
            seen.add(key)

            order += 1
            steps.append({
                "title":        etape[:255],
                "instructions": methode,
                "order":        order,
            })

    return steps


def extract_steps_from_excel(file_path):
    """Read rows from the first sheet of an Excel file as IGT steps.

    The header row is auto-detected. Expected column names (case-insensitive):
      Step title    : Step | Étape | Etape | Name | Nom | Task
      Instructions  : Instructions | Method | Méthode | Description
      Notes (opt.)  : Notes | Remarks | Remarques | Comments

    Falls back to column A = title, column B = instructions when no
    matching headers are found.
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        print("  Warning: openpyxl not installed — Excel step extraction skipped")
        return []

    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
    except Exception as e:
        print(f"  Warning: could not open Excel for step extraction: {e}")
        return []

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    if len(rows) < 2:
        return []

    # Auto-detect header columns
    headers = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
    title_col  = _col_index(headers, "step", "étape", "etape", "name", "nom", "task", "tâche")
    instr_col  = _col_index(headers, "instruction", "method", "méthode", "description", "procédure")
    notes_col  = _col_index(headers, "note", "remark", "remarque", "comment")

    if title_col == -1 and instr_col == -1:
        title_col, instr_col = 0, 1  # fallback: A=title, B=instructions

    def _cell(row, idx):
        if idx < 0 or idx >= len(row) or row[idx] is None:
            return ""
        return str(row[idx]).strip()

    steps = []
    for order, row in enumerate(rows[1:], start=1):
        title  = _cell(row, title_col)
        instr  = _cell(row, instr_col)
        notes  = _cell(row, notes_col)

        if notes:
            instr = f"{instr}\n\nNote: {notes}".strip()

        if not (title or instr):
            continue

        steps.append({
            "title":        title[:255],
            "instructions": instr,
            "order":        order,
        })

    return steps


# ── Main processing ────────────────────────────────────────────────────────────

def process_igt(file_path, instance, username, password, assign_type):
    """Process one source file → create IGT Standard + steps in ServiceNow.

    Returns (igt_number, error_message).  error_message is None on success.
    """
    ext   = file_path.suffix.lower()
    title = file_path.stem.replace("_", " ").replace("-", " ").title()

    # ── 1. Extract HTML content ────────────────────────────────────────────────
    print("  Extracting content...", end=" ")
    try:
        html = upload_to_kb.extract_html(file_path)
    except Exception as e:
        print(f"FAILED ({e})")
        return None, str(e)

    if not html or not html.strip():
        print("FAILED (no content)")
        return None, "No content could be extracted"
    print(f"OK ({len(html) // 1024} KB)")

    # ── 2. Extract procedure steps ─────────────────────────────────────────────
    steps = []
    if ext == ".docx":
        steps = extract_steps_from_docx(file_path)
        if steps:
            print(f"  Found {len(steps)} procedure step(s) in DOCX tables")
    elif ext == ".xlsx":
        steps = extract_steps_from_excel(file_path)
        if steps:
            print(f"  Found {len(steps)} step row(s) in Excel")

    # ── 3. Create IGT Standard record ─────────────────────────────────────────
    print("  Creating IGT Standard...", end=" ")
    sys_id, number = create_igt_standard(instance, username, password, title, assign_type)
    if not sys_id:
        print(f"FAILED ({str(number)[:100]})")
        return None, str(number)[:200]
    print(f"OK ({number})")

    # ── 4. Upload embedded base64 images as SN attachments ────────────────────
    if "data:image/" in html:
        print("  Uploading embedded images...", end=" ")
        html, img_count = replace_base64_images(
            html, instance, username, password, sys_id, file_path.stem,
            table_name="sn_icw_igt_standard",
        )
        print(f"{img_count} image(s)")

    # ── 5. Update IGT Standard with final HTML ─────────────────────────────────
    print("  Updating IGT content...", end=" ")
    if not update_igt_standard(instance, username, password, sys_id, html):
        print("FAILED")
        return None, "Standard created but content update failed"
    print("OK")

    # ── 6. Create individual step records (sn_icw_std_task) ───────────────────
    if steps:
        print(f"  Creating {len(steps)} step record(s)...", end=" ")
        ok_steps = fail_steps = 0
        for step in steps:
            step_sys_id, _ = create_igt_step(
                instance, username, password,
                standard_sys_id=sys_id,
                title=step["title"],
                instructions=step["instructions"],
                order=step["order"],
            )
            if step_sys_id:
                ok_steps += 1
            else:
                fail_steps += 1
        status = f"{ok_steps} OK"
        if fail_steps:
            status += f", {fail_steps} FAILED (check field names for sn_icw_std_task)"
        print(status)

    return number, None


def main():
    if len(sys.argv) < 2:
        print("Usage: python igt_to_kb.py <folder_path>")
        sys.exit(1)

    folder_path = Path(sys.argv[1])
    if not folder_path.is_dir():
        print(f"ERROR: '{folder_path}' is not a valid directory.")
        sys.exit(1)

    instance, username, password, assign_type = get_config()

    files = [
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        print(f"No supported files found in '{folder_path}'.")
        print(f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(0)

    print(f"Found {len(files)} file(s) to process as IGT Standards.")
    print(f"Assignment type: {assign_type}\n")

    results = {"success": [], "failed": []}

    for file_path in sorted(files):
        print(f"[igt] {file_path.name}")
        try:
            number, error = process_igt(file_path, instance, username, password, assign_type)
            if number:
                results["success"].append((file_path.name, number))
            else:
                results["failed"].append((file_path.name, error))
        except Exception as e:
            print(f"  ERROR: {e}")
            results["failed"].append((file_path.name, str(e)))
        print()

    print("--- Summary ---")
    print(f"Successful: {len(results['success'])}")
    print(f"Failed:     {len(results['failed'])}")

    if results["success"]:
        print("\nCreated IGT Standards:")
        for name, number in results["success"]:
            print(f"  - {name} -> {number}")

    if results["failed"]:
        print("\nFailed files:")
        for name, reason in results["failed"]:
            print(f"  - {name}: {reason}")


if __name__ == "__main__":
    main()
