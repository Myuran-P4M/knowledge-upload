---
name: sn-kb-image
description: Upload photos of paper documents to a ServiceNow Knowledge Base. Uses Claude Vision API to extract text and formatting from document images, then creates KB articles with both the original image and extracted content.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash(python *), Bash(pip *), Read, Glob
argument-hint: [folder-path]
---

# ServiceNow KB Image Upload (Vision)

Upload document photos from a folder to ServiceNow as Knowledge Base articles using Claude Vision API.

## Usage

`/sn-kb-image C:\path\to\images`

## What it does

1. Scans the folder for supported image files (JPG, JPEG, PNG, GIF, WEBP)
2. Sends each image to the Claude Vision API to extract text with formatting
3. Creates a KB article containing the original image and the extracted content
4. Uploads images as ServiceNow attachments (base64 won't render in SN)

## Required Environment Variables

Set these in `sn-kb-image/.env`:
- `SN_INSTANCE` — ServiceNow instance URL (e.g., `https://myinstance.service-now.com`)
- `SN_USERNAME` — ServiceNow username
- `SN_PASSWORD` — ServiceNow password
- `SN_KB_SYS_ID` — sys_id of the target Knowledge Base
- `ANTHROPIC_API_KEY` — Anthropic API key (get one at https://console.anthropic.com/)
- `CLAUDE_MODEL` — *(optional)* Claude model to use (defaults to `claude-sonnet-4-5-20250929`)

## Execution

Run the upload script against the provided folder:

```bash
python "$SKILL_PATH/image_to_kb.py" $ARGUMENTS
```

If the script fails due to missing dependencies, install them first:

```bash
pip install -r "$SKILL_PATH/requirements.txt"
```

Report the results back to the user, including which files succeeded and which failed.
