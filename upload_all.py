"""Unified upload dispatcher — routes files to the right extraction pipeline.

Digital documents (.pdf, .docx, .xlsx, .pptx) -> sn-kb-upload (local extraction)
Document photos (.jpg, .jpeg, .png, .gif, .webp) -> sn-kb-image (Claude Vision API)
"""

import os
import sys
import base64
from pathlib import Path
from dotenv import load_dotenv

_script_dir = Path(__file__).parent
load_dotenv(_script_dir / ".env")

# Add both skill directories to sys.path for imports
sys.path.insert(0, str(_script_dir / "sn-kb-upload"))
sys.path.insert(0, str(_script_dir / "sn-kb-image"))

import upload_to_kb
import image_to_kb

from sn_kb_shared import (
    replace_base64_images,
    create_article,
    update_article,
)

DIGITAL_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALL_EXTENSIONS = DIGITAL_EXTENSIONS | IMAGE_EXTENSIONS


def get_config(need_api_key):
    """Validate env vars. Only require ANTHROPIC_API_KEY when image files are present."""
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
    if need_api_key and not api_key:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        if "ANTHROPIC_API_KEY" in missing:
            print("  ANTHROPIC_API_KEY is required because image files were found.")
            print("  Get an API key at https://console.anthropic.com/")
        sys.exit(1)

    return instance, username, password, kb_sys_id, api_key, model


def process_digital(file_path, instance, username, password, kb_sys_id):
    """Process a digital document via the sn-kb-upload pipeline."""
    html = upload_to_kb.extract_html(file_path)
    if not html or not html.strip():
        return None, "No content could be extracted"

    title = file_path.stem.replace("_", " ").replace("-", " ").title()

    # Create article with placeholder
    print("  Creating KB article...", end=" ")
    article_sys_id, number = create_article(
        instance, username, password, kb_sys_id, title, "<p>Uploading content...</p>"
    )
    if not article_sys_id:
        print(f"FAILED ({number[:100]})")
        return None, number[:200]
    print(f"OK ({number})")

    # Upload embedded images as attachments
    if "data:image/" in html:
        print("  Uploading embedded images...", end=" ")
        html, img_count = replace_base64_images(
            html, instance, username, password, article_sys_id, file_path.stem
        )
        print(f"{img_count} image(s)")

    # Update article body
    print("  Updating article content...", end=" ")
    if update_article(instance, username, password, article_sys_id, html):
        print("OK")
        return number, None
    else:
        print("FAILED")
        return None, "Article created but body update failed"


def process_image(file_path, instance, username, password, kb_sys_id, api_key, model):
    """Process a document photo via the sn-kb-image pipeline (Claude Vision API)."""
    # Validate and prepare image
    print("  Validating image...", end=" ")
    media_type, api_b64, original_bytes, orig_mime = image_to_kb.validate_and_prepare_image(file_path)
    print("OK")

    # Extract content via Claude Vision API
    print("  Extracting content via Claude Vision API...", end=" ")
    extracted_html = image_to_kb.extract_html_from_image(api_key, model, media_type, api_b64)
    if not extracted_html or not extracted_html.strip():
        print("FAILED")
        return None, "No content extracted from image"
    print("OK")

    # Build article HTML (original image + extracted content)
    orig_b64 = base64.b64encode(original_bytes).decode("ascii")
    article_html = image_to_kb.build_article_html(extracted_html, orig_b64, orig_mime, file_path.name)

    title = file_path.stem.replace("_", " ").replace("-", " ").title()

    # Create draft KB article
    print("  Creating KB article...", end=" ")
    article_sys_id, number = create_article(
        instance, username, password, kb_sys_id, title, "<p>Uploading content...</p>"
    )
    if not article_sys_id:
        print(f"FAILED ({number[:100]})")
        return None, number[:200]
    print(f"OK ({number})")

    # Upload base64 images as SN attachments
    print("  Uploading images as attachments...", end=" ")
    article_html, img_count = replace_base64_images(
        article_html, instance, username, password, article_sys_id, file_path.stem
    )
    print(f"{img_count} image(s)")

    # Update article body
    print("  Updating article content...", end=" ")
    if update_article(instance, username, password, article_sys_id, article_html):
        print("OK")
        return number, None
    else:
        print("FAILED")
        return None, "Article created but body update failed"


def main():
    if len(sys.argv) < 2:
        print("Usage: python upload_all.py <folder_path>")
        sys.exit(1)

    folder_path = Path(sys.argv[1])
    if not folder_path.is_dir():
        print(f"ERROR: '{folder_path}' is not a valid directory.")
        sys.exit(1)

    # Scan and classify files
    digital_files = []
    image_files = []
    for f in folder_path.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in DIGITAL_EXTENSIONS:
            digital_files.append(f)
        elif ext in IMAGE_EXTENSIONS:
            image_files.append(f)

    total = len(digital_files) + len(image_files)
    if total == 0:
        print(f"No supported files found in '{folder_path}'.")
        print(f"Supported types: {', '.join(sorted(ALL_EXTENSIONS))}")
        sys.exit(0)

    print(f"Found {total} file(s): {len(digital_files)} digital, {len(image_files)} image(s)")

    # Validate config — only require API key if there are images
    need_api_key = len(image_files) > 0
    instance, username, password, kb_sys_id, api_key, model = get_config(need_api_key)

    if image_files:
        print(f"Vision model: {model}")
    print()

    results = {"success": [], "failed": []}

    # Process digital files first, then images
    for file_path in sorted(digital_files):
        print(f"[digital] {file_path.name}")
        try:
            number, error = process_digital(file_path, instance, username, password, kb_sys_id)
            if number:
                results["success"].append((file_path.name, number, "digital"))
            else:
                results["failed"].append((file_path.name, error))
        except Exception as e:
            print(f"  ERROR ({e})")
            results["failed"].append((file_path.name, str(e)))
        print()

    for file_path in sorted(image_files):
        print(f"[vision] {file_path.name}")
        try:
            number, error = process_image(
                file_path, instance, username, password, kb_sys_id, api_key, model
            )
            if number:
                results["success"].append((file_path.name, number, "vision"))
            else:
                results["failed"].append((file_path.name, error))
        except Exception as e:
            print(f"  ERROR ({e})")
            results["failed"].append((file_path.name, str(e)))
        print()

    # Summary
    print("--- Summary ---")
    print(f"Successful: {len(results['success'])}")
    print(f"Failed:     {len(results['failed'])}")

    if results["success"]:
        print("\nUploaded articles:")
        for name, number, pipeline in results["success"]:
            print(f"  [{pipeline}] {name} -> {number}")

    if results["failed"]:
        print("\nFailed files:")
        for name, reason in results["failed"]:
            print(f"  - {name}: {reason}")


if __name__ == "__main__":
    main()
