import os
import sys
import re
import html as html_mod
import base64
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the same directory as this script
load_dotenv(Path(__file__).parent.parent / ".env")

# Add parent directory to path for shared module
sys.path.insert(0, str(Path(__file__).parent.parent))
from sn_kb_shared import (
    upload_attachment,
    replace_base64_images,
    create_article,
    update_article,
)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# Claude Vision API max dimension
MAX_IMAGE_DIMENSION = 1568

# Max file size for upload (20 MB)
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def get_config():
    """Load and validate environment variables."""
    instance = os.environ.get("SN_INSTANCE", "").rstrip("/")
    username = os.environ.get("SN_USERNAME", "")
    password = os.environ.get("SN_PASSWORD", "")
    kb_sys_id = os.environ.get("SN_KB_SYS_ID", "")
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")

    missing = []
    if not instance:
        missing.append("SN_INSTANCE")
    if not username:
        missing.append("SN_USERNAME")
    if not password:
        missing.append("SN_PASSWORD")
    if not kb_sys_id:
        missing.append("SN_KB_SYS_ID")
    if not api_key:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        if "ANTHROPIC_API_KEY" in missing:
            print("  Get an API key at https://console.anthropic.com/")
        sys.exit(1)

    return instance, username, password, kb_sys_id, api_key, model


def validate_and_prepare_image(file_path):
    """Open image with Pillow, validate format, resize if needed for Claude Vision API.

    Returns (media_type, base64_for_api, original_bytes, original_mime).
    The API version is resized to fit within MAX_IMAGE_DIMENSION.
    The original bytes are kept at full resolution for the article.
    """
    from PIL import Image
    import io

    # Check file size before processing
    file_size = file_path.stat().st_size
    if file_size == 0:
        raise ValueError(f"Image file is empty: {file_path.name}")
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"Image file too large ({file_size / (1024*1024):.1f} MB). "
            f"Max supported: {MAX_FILE_SIZE_BYTES / (1024*1024):.0f} MB"
        )

    img = Image.open(file_path)
    img.verify()  # Verify image integrity
    img = Image.open(file_path)  # Re-open after verify (verify closes the image)

    # Apply EXIF orientation so rotated phone photos are upright
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # No EXIF data or unsupported — use image as-is

    # Map format to media type
    format_map = {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "GIF": "image/gif",
        "WEBP": "image/webp",
    }
    img_format = img.format or "PNG"
    media_type = format_map.get(img_format, "image/png")

    # Read original bytes for the article (full resolution)
    original_bytes = file_path.read_bytes()

    # Resize for API if needed
    width, height = img.size
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        ratio = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    # Convert to bytes for API
    buf = io.BytesIO()
    save_format = img_format if img_format in ("JPEG", "PNG", "GIF", "WEBP") else "PNG"
    if save_format == "JPEG":
        img = img.convert("RGB")  # JPEG doesn't support alpha
    img.save(buf, format=save_format)
    api_bytes = buf.getvalue()
    api_b64 = base64.standard_b64encode(api_bytes).decode("ascii")

    return media_type, api_b64, original_bytes, media_type


def extract_html_from_image(api_key, model, media_type, b64_data):
    """Send image to Claude Vision API and extract formatted HTML content."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    prompt = (
        "You are a document digitization specialist. Analyze this document image and "
        "extract ALL text content, preserving the original formatting as closely as possible.\n\n"
        "CRITICAL — Text accuracy:\n"
        "- Extract ALL text EXACTLY as it appears — do NOT guess, infer, or hallucinate text you cannot read clearly.\n"
        "- If text is too small or blurry to read with certainty, output [illisible] rather than guessing.\n"
        "- Include EVERY piece of text: headers, body, fine print, copyright notices, "
        "reference numbers, page numbers, URLs, footnotes — nothing should be omitted.\n"
        "- Preserve the original language of the document (likely French). Do NOT translate any text.\n"
        "- Preserve accented characters exactly: é, è, ê, ë, à, â, ç, ù, û, ô, î, ï, etc.\n\n"
        "CRITICAL — Bold/weight accuracy:\n"
        "- Only use <b> for text that is visibly THICKER/HEAVIER in the original image.\n"
        "- Most body text, list items, and paragraphs are regular weight — do NOT default to bold.\n"
        "- Look carefully at each text element: if it appears the same weight as surrounding body text, it is NOT bold.\n\n"
        "CRITICAL — Table detection:\n"
        "- Look carefully for tabular data: rows of aligned values, column headers, grid lines, "
        "or data that is clearly arranged in columns even without visible borders.\n"
        "- Financial statements, invoices, lab results, and forms often contain tables — "
        "always render these as <table> elements, not as loose text or lists.\n"
        "- For borderless tabular data, infer the column structure from alignment and use "
        "<table> with appropriate column widths.\n\n"
        "CRITICAL — Form fields:\n"
        "- For checkboxes, use [x] for checked and [ ] for unchecked.\n"
        "- For filled-in form fields, show the label followed by the handwritten/typed value.\n"
        "- For signatures, use [signature] as placeholder.\n\n"
        "HTML rules:\n"
        "1. Output raw HTML only — no markdown code fences, no ```html wrapper, no <html>/<body> tags.\n"
        "2. Use ONLY inline styles (style=\"...\") — never use CSS classes or <style> blocks.\n"
        "3. Do NOT use display:flex or display:grid — these are not supported in the target system. "
        "Use <table> elements for all multi-column layouts.\n"
        "4. Preserve document structure: headings (<h1>-<h4>), tables (<table>), lists (<ul>/<ol>), paragraphs (<p>).\n"
        "5. For data tables, use <table border=\"1\" cellpadding=\"6\" style=\"border-collapse:collapse;width:100%\">.\n"
        "6. For layout tables (e.g. warning boxes with icon + text side by side), use <table> with no border.\n"
        "7. Preserve colors, italic, underline using inline styles and <i>/<u> tags.\n"
        "8. Preserve text alignment (center, right) using style=\"text-align:center\" etc.\n"
        "9. For colored backgrounds, use style=\"background-color:#hex;padding:4px 8px\".\n"
        "10. Do NOT generate SVG, emoji characters, or attempt to recreate icons/graphics/logos. "
        "For non-text visual elements (icons, symbols, logos), insert a brief text description in "
        "square brackets, e.g. [yellow triangle with lightning bolt icon] or [blue circle with person reading manual icon].\n"
        "11. Use readable font sizes — body text should be 13-14px, headings proportionally larger.\n"
        "12. Output the HTML content directly — start with the first HTML tag, nothing else before or after.\n"
        "13. For multi-section documents (e.g. multiple pages in one photo), separate sections with "
        "<hr style=\"border:1px solid #ccc;margin:20px 0\">.\n"
        "14. Preserve document metadata when visible (dates, reference numbers, sender/recipient info) — "
        "these are often the most important parts of administrative documents."
    )

    message = client.messages.create(
        model=model,
        max_tokens=16384,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
    )

    # Warn if output was truncated due to max_tokens
    if message.stop_reason == "max_tokens":
        print("\n    WARNING: Vision API output was truncated (hit max_tokens limit).", end=" ")

    # Extract text from response
    raw_html = ""
    for block in message.content:
        if block.type == "text":
            raw_html += block.text

    raw_html = _strip_code_fences(raw_html)

    return raw_html


def _strip_code_fences(text):
    """Remove markdown code fences from Vision API output.

    Handles: ```html ... ```, ``` ... ```, ```HTML ... ```,
    and any leading/trailing whitespace variants.
    """
    text = text.strip()

    # Try to match opening ``` with optional language tag
    match = re.match(r'^```\w*\s*\n?', text, re.IGNORECASE)
    if match:
        text = text[match.end():]

    # Remove trailing ``` (possibly with trailing whitespace)
    text = re.sub(r'\n?```\s*$', '', text)

    return text.strip()


def build_article_html(extracted_html, original_b64, mime_type, filename):
    """Combine original image and extracted HTML into a complete article body.

    Layout:
    - Original document photo at top (full width, centered, with border)
    - Separator line
    - "Content extracted from document image above" caption
    - Extracted HTML content
    """
    safe_filename = html_mod.escape(filename, quote=True)
    article = (
        f'<div style="text-align:center;margin-bottom:20px">'
        f'<img src="data:{mime_type};base64,{original_b64}" '
        f'style="max-width:100%;border:1px solid #ccc" alt="{safe_filename}" />'
        f'</div>'
        f'<hr style="border:1px solid #ccc;margin:20px 0" />'
        f'<p style="text-align:center;font-style:italic;color:#666;margin-bottom:20px">'
        f'Content extracted from document image above</p>'
        f'{extracted_html}'
    )
    return article


def main():
    if len(sys.argv) < 2:
        print("Usage: python image_to_kb.py <folder_path>")
        sys.exit(1)

    folder_path = Path(sys.argv[1])
    if not folder_path.is_dir():
        print(f"ERROR: '{folder_path}' is not a valid directory.")
        sys.exit(1)

    instance, username, password, kb_sys_id, api_key, model = get_config()

    files = [
        f for f in folder_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not files:
        print(f"No supported image files found in '{folder_path}'.")
        print(f"Supported types: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")
        sys.exit(0)

    print(f"Found {len(files)} image(s) to process.")
    print(f"Using model: {model}\n")

    results = {"success": [], "failed": []}
    sorted_files = sorted(files)
    total_files = len(sorted_files)

    for idx, file_path in enumerate(sorted_files, 1):
        print(f"[{idx}/{total_files}] Processing: {file_path.name}...")

        try:
            # Step 1: Validate and prepare image
            print("  Validating image...", end=" ")
            media_type, api_b64, original_bytes, orig_mime = validate_and_prepare_image(file_path)
            print("OK")

            # Step 2: Send to Claude Vision API for text extraction
            print("  Extracting content via Claude Vision API...", end=" ")
            extracted_html = extract_html_from_image(api_key, model, media_type, api_b64)
            if not extracted_html or not extracted_html.strip():
                print("FAILED (no content extracted)")
                results["failed"].append((file_path.name, "No content extracted from image"))
                continue
            print("OK")

            # Step 3: Build the article HTML (original image + extracted content)
            orig_b64 = base64.b64encode(original_bytes).decode("ascii")
            article_html = build_article_html(extracted_html, orig_b64, orig_mime, file_path.name)

            title = file_path.stem.replace("_", " ").replace("-", " ").title()

            # Step 4: Create draft KB article with placeholder
            print("  Creating KB article...", end=" ")
            article_sys_id, number = create_article(
                instance, username, password, kb_sys_id, title, "<p>Uploading content...</p>"
            )

            if not article_sys_id:
                print(f"FAILED ({number[:100]})")
                results["failed"].append((file_path.name, number[:200]))
                continue
            print(f"OK ({number})")

            # Step 5: Upload base64 images as SN attachments
            print("  Uploading images as attachments...", end=" ")
            article_html, img_count = replace_base64_images(
                article_html, instance, username, password, article_sys_id, file_path.stem
            )
            print(f"{img_count} image(s) uploaded")

            # Step 6: Update article body with final HTML (attachment URLs)
            print("  Updating article content...", end=" ")
            if update_article(instance, username, password, article_sys_id, article_html):
                print("OK")
                results["success"].append((file_path.name, number))
            else:
                print("FAILED (could not update article body)")
                results["failed"].append((file_path.name, "Article created but body update failed"))

        except Exception as e:
            print(f"  ERROR ({e})")
            results["failed"].append((file_path.name, str(e)))

        print()

    print("--- Summary ---")
    print(f"Successful: {len(results['success'])}")
    print(f"Failed:     {len(results['failed'])}")

    if results["success"]:
        print("\nUploaded articles:")
        for name, number in results["success"]:
            print(f"  - {name} -> {number}")

    if results["failed"]:
        print("\nFailed files:")
        for name, reason in results["failed"]:
            print(f"  - {name}: {reason}")


if __name__ == "__main__":
    main()
