---
name: sn-kb-upload
description: Upload documents from a folder to a ServiceNow Knowledge Base. Extracts text from PDFs, Word, Excel, PowerPoint, and images (OCR), then creates KB articles via the ServiceNow Table API.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash(python *), Bash(pip *), Read, Glob
argument-hint: [folder-path]
---

# ServiceNow KB Upload

Upload all documents in a folder to ServiceNow as Knowledge Base articles.

## Usage

`/sn-kb-upload C:\path\to\documents`

## What it does

1. Scans the folder for supported files (PDF, DOCX, XLSX, PPTX, PNG, JPG, JPEG)
2. Extracts text content from each file
3. Creates a Knowledge Base article in ServiceNow for each file

## Required Environment Variables

Set these before running:
- `SN_INSTANCE` — ServiceNow instance URL (e.g., `https://myinstance.service-now.com`)
- `SN_USERNAME` — ServiceNow username
- `SN_PASSWORD` — ServiceNow password
- `SN_KB_SYS_ID` — sys_id of the target Knowledge Base

## Execution

Run the upload script against the provided folder:

```bash
python "$SKILL_PATH/upload_to_kb.py" $ARGUMENTS
```

If the script fails due to missing dependencies, install them first:

```bash
pip install -r "$SKILL_PATH/requirements.txt"
```

Report the results back to the user, including which files succeeded and which failed.
