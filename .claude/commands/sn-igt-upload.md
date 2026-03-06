Upload procedure documents from **$ARGUMENTS** to ServiceNow ICW as Industrial Guided Task (IGT) Standards.

Work from the root of the `SN knowledge upload-Claude` project directory.

## What will be created in ServiceNow

For each DOCX or XLSX file found:

| Record | Table | Details |
|--------|-------|---------|
| IGT Standard | `sn_icw_igt_standard` | One per file, with owner_group / location / category references |
| Sections | `sn_smart_asmt_section` | One per unique **ETAPE** value in the document |
| Questions | `sn_smart_asmt_question` | One Radio button question per step — label = **METHODE** instruction text |
| Choices | `sn_smart_asmt_response_option` | **"Fait"** and **"Non-fait"** on every question |
| Photos | Attachments on `sn_smart_asmt_question` | Images from the **PHOTO** column set as guidance |

---

## Step 1 — Verify environment

Check that both `.env` files are present and complete:

```bash
python -c "
from dotenv import load_dotenv; import os, sys
load_dotenv('.env')
load_dotenv('sn-igt-upload/.env', override=True)
required = {
    'SN_INSTANCE':               'shared .env',
    'SN_USERNAME':               'shared .env',
    'SN_PASSWORD':               'shared .env',
    'SN_IGT_OWNER_GROUP':        'sn-igt-upload/.env',
    'SN_IGT_LOCATION':           'sn-igt-upload/.env',
    'SN_IGT_FUNCTIONAL_LOCATIONS':'sn-igt-upload/.env',
    'SN_IGT_CATEGORY':           'sn-igt-upload/.env',
}
missing = {k: v for k, v in required.items() if not os.environ.get(k)}
if missing:
    for k, src in missing.items():
        print(f'  MISSING {k}  (add to {src})')
    sys.exit(1)
print(f'OK — {os.environ[\"SN_INSTANCE\"]}')
"
```

Stop and tell the user which variables are missing if the check fails.

---

## Step 2 — Preview what will be extracted

Run the extraction preview tool to show the user what steps will be found **before** making any API calls:

```bash
python sn-igt-skill/extract_steps.py "$ARGUMENTS"
```

Parse the JSON output and present a readable summary table, for example:

| File | Steps | Sections (ETAPEs) | Photos |
|------|-------|-------------------|--------|
| my_doc.docx | 107 | 51 | 95 |

Also show the first 3 ETAPE names so the user can sanity-check column detection.

If no files are found or no steps are detected, stop and explain why.

---

## Step 3 — Upload

Run the pipeline:

```bash
python upload_all.py "$ARGUMENTS"
```

Watch the output line by line. The expected output per file is:
```
[igt] <filename>
  Found N step(s), N photo(s)
  Creating IGT Standard... OK (IGTSXXXXXX)
  Creating N question(s)... N OK
  Sections created: N
```

---

## Step 4 — Handle any failures

If any questions or sections failed:

1. Query ServiceNow to see what was already created
2. Identify the cause from the error message
3. Retry the failed records if appropriate
4. Explain what happened to the user

---

## Step 5 — Report results

For every IGT Standard created, report:

```
✅ my_doc.docx → IGTSXXXXXX
   Sections : 51
   Questions: 107  (each with Fait / Non-fait choices)
   Photos   : 95 attached as question guidance
   View     : https://<instance>/sn_icw_igt_standard.do?sys_id=<sys_id>
```

Fetch the created record from ServiceNow to confirm all reference fields
(owner_group, location, functional_locations, category) were set correctly,
and include them in the report.
