# sn-kb-image — Vision-Based Document Photo Upload

Upload photos of paper documents to a ServiceNow Knowledge Base. Uses Claude's Vision API to extract text with formatting from document images, then creates KB articles containing both the original photo and the extracted content.

## When to Use This vs sn-kb-upload

| | sn-kb-upload | sn-kb-image |
|---|---|---|
| **Input** | Digital documents (PDF, DOCX, XLSX, PPTX) | Photos of paper documents |
| **Extraction** | PyMuPDF text extraction, mammoth, openpyxl | Claude Vision API (AI-powered OCR) |
| **Best for** | Born-digital files with selectable text | Scanned docs, phone photos, handwritten notes |
| **Cost** | Free (local processing) | ~$0.01-0.05 per image (Anthropic API) |
| **Accuracy** | Exact text extraction | AI interpretation (very high but not perfect) |

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get an Anthropic API key

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to API Keys > Create Key
4. Copy the key (starts with `sk-ant-...`)

### 3. Configure .env

Edit `sn-kb-image/.env` and fill in your credentials:

```env
SN_INSTANCE=https://your-instance.service-now.com
SN_USERNAME=admin
SN_PASSWORD=your-password
SN_KB_SYS_ID=your-kb-sys-id

ANTHROPIC_API_KEY=sk-ant-your-key-here

# Optional: override the model (defaults to claude-sonnet-4-5-20250929)
# CLAUDE_MODEL=claude-sonnet-4-5-20250929
```

## Usage

### Command line

```bash
# Upload all images from a folder
python claude/sn-kb-image/image_to_kb.py "path/to/images"
```

### Claude Code skill

```
/sn-kb-image "path/to/images"
```

## Supported Image Types

- `.jpg` / `.jpeg`
- `.png`
- `.gif`
- `.webp`

## How It Works

1. **Validate & resize** — Opens the image with Pillow, resizes to fit Claude Vision API limits (max 1568px) while keeping the original at full resolution for the article
2. **Vision extraction** — Sends the image to Claude with a detailed prompt to extract all text as styled HTML
3. **Build article** — Combines the original full-resolution photo (top) with extracted content (below), separated by a divider
4. **Create draft article** — Creates a KB article in ServiceNow in draft state
5. **Upload attachments** — Uploads base64 images as SN attachments (required — base64 won't render in SN)
6. **Update article** — Replaces base64 src references with SN attachment URLs

## Article Layout

Each article contains:

```
+------------------------------------------+
|          [Original Document Photo]        |
|          (full width, centered)           |
+------------------------------------------+
|  ────────────────────────────────────────  |
|  "Content extracted from document above"  |
|                                           |
|  [Extracted headings, tables, text...]    |
+------------------------------------------+
```

## Cost Estimates

Using Claude Sonnet (default):
- ~$0.003 per 1000 input tokens (images are ~1600 tokens for a typical document photo)
- ~$0.015 per 1000 output tokens
- **Typical cost per document: $0.01 - $0.05** depending on content density

## Troubleshooting

- **"Missing ANTHROPIC_API_KEY"** — Add your key to `.env` (see Setup above)
- **"No content extracted"** — The image may be too blurry, dark, or not contain readable text
- **Large images are slow** — Images are resized for the API but originals are preserved in the article
- **SN attachment fails** — Check that your SN instance is reachable and credentials are valid
