# ServiceNow KB Upload

A Claude Code skill that uploads documents from a local folder to a ServiceNow Knowledge Base.

## Supported File Types

- PDF (`.pdf`)
- Word (`.docx`)
- Excel (`.xlsx`)
- PowerPoint (`.pptx`)
- Images (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`) — requires Tesseract OCR

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install Tesseract (optional, for image OCR)

Download from: https://github.com/tesseract-ocr/tesseract

### 3. Set environment variables

```bash
set SN_INSTANCE=https://yourinstance.service-now.com
set SN_USERNAME=your_username
set SN_PASSWORD=your_password
set SN_KB_SYS_ID=your_kb_sys_id
```

### 4. Install as Claude Code skill

Copy the `sn-kb-upload` folder to `~/.claude/skills/sn-kb-upload/`.

## Usage

### As a Claude Code skill

```
/sn-kb-upload C:\path\to\documents
```

### Standalone

```bash
python upload_to_kb.py C:\path\to\documents
```

## How It Works

1. Scans the target folder for supported file types
2. Extracts text content from each document
3. Creates a Knowledge Base article (in **draft** state) for each file via the ServiceNow Table API
4. Reports success/failure for each file
