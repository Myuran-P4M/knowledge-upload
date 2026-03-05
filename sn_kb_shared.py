"""Shared utilities for ServiceNow KB upload pipelines.

Contains common functions used by both the digital document pipeline (sn-kb-upload)
and the vision-based image pipeline (sn-kb-image).
"""

import re
import base64
import time
import requests


# Retry settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds


def retry_on_failure(func, *args, retries=MAX_RETRIES, description="API call", **kwargs):
    """Retry a function with exponential backoff on transient failures."""
    last_exception = None
    for attempt in range(retries + 1):
        try:
            return func(*args, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            last_exception = e
            if attempt < retries:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"\n    Retry {attempt + 1}/{retries} for {description} in {delay}s...", end=" ")
                time.sleep(delay)
            else:
                raise
    raise last_exception


def _upload_attachment_once(instance, username, password, table_sys_id, file_name, file_bytes, content_type, table_name="kb_knowledge"):
    """Single attempt to upload a file as an attachment."""
    url = (
        f"{instance}/api/now/attachment/file"
        f"?table_name={table_name}&table_sys_id={table_sys_id}&file_name={file_name}"
    )
    headers = {
        "Content-Type": content_type,
        "Accept": "application/json",
    }
    response = requests.post(
        url,
        auth=(username, password),
        headers=headers,
        data=file_bytes,
        timeout=30,
    )
    if response.status_code in (200, 201):
        result = response.json().get("result", {})
        att_sys_id = result.get("sys_id", "")
        return f"{instance}/sys_attachment.do?sys_id={att_sys_id}"
    print(f"\n    WARNING: Attachment API returned {response.status_code} for {file_name}")
    return None


def upload_attachment(instance, username, password, table_sys_id, file_name, file_bytes, content_type, table_name="kb_knowledge"):
    """Upload a file as an attachment with retry on transient failures."""
    return retry_on_failure(
        _upload_attachment_once,
        instance, username, password, table_sys_id, file_name, file_bytes, content_type, table_name,
        description=f"attachment upload ({file_name})",
    )


def replace_base64_images(html, instance, username, password, article_sys_id, file_stem, table_name="kb_knowledge"):
    """Find base64 images in HTML, upload them as attachments, replace src with URLs."""
    pattern = r'src="data:(image/[^;]+);base64,([^"]+)"'
    img_counter = [0]

    def replacer(match):
        content_type = match.group(1)
        b64_data = match.group(2)
        img_counter[0] += 1

        ext_map = {
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/jpg": "jpg",
            "image/bmp": "bmp",
            "image/tiff": "tiff",
            "image/gif": "gif",
            "image/webp": "webp",
        }
        ext = ext_map.get(content_type, "png")
        file_name = f"{file_stem}_img{img_counter[0]}.{ext}"

        try:
            img_bytes = base64.b64decode(b64_data)
            att_url = upload_attachment(
                instance, username, password, article_sys_id,
                file_name, img_bytes, content_type, table_name,
            )
            if att_url:
                return f'src="{att_url}"'
            else:
                print(f"\n    WARNING: Attachment upload failed for {file_name}, keeping base64")
        except Exception as e:
            print(f"\n    WARNING: Failed to process image {file_name}: {e}")

        return match.group(0)

    updated_html = re.sub(pattern, replacer, html)
    return updated_html, img_counter[0]


def _create_article_once(instance, username, password, kb_sys_id, title, body):
    """Single attempt to create a KB article."""
    url = f"{instance}/api/now/table/kb_knowledge"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "short_description": title,
        "text": body,
        "kb_knowledge_base": kb_sys_id,
        "workflow_state": "draft",
    }

    response = requests.post(
        url,
        auth=(username, password),
        headers=headers,
        json=payload,
        timeout=60,
    )

    if response.status_code in (200, 201):
        result = response.json().get("result", {})
        return result.get("sys_id", ""), result.get("number", "")
    else:
        return None, response.text


def create_article(instance, username, password, kb_sys_id, title, body):
    """Create a KB article with retry on transient failures."""
    return retry_on_failure(
        _create_article_once,
        instance, username, password, kb_sys_id, title, body,
        description="article creation",
    )


def _update_article_once(instance, username, password, sys_id, body):
    """Single attempt to update the KB article body."""
    url = f"{instance}/api/now/table/kb_knowledge/{sys_id}"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    response = requests.patch(
        url,
        auth=(username, password),
        headers=headers,
        json={"text": body},
        timeout=60,
    )
    return response.status_code in (200, 201)


def update_article(instance, username, password, sys_id, body):
    """Update the KB article body with retry on transient failures."""
    return retry_on_failure(
        _update_article_once,
        instance, username, password, sys_id, body,
        description="article update",
    )


# ── ICW Industrial Guided Task (IGT) functions ────────────────────────────────

_HEADERS_JSON = {"Content-Type": "application/json", "Accept": "application/json"}


def _create_igt_standard_once(instance, username, password, title, assignment_type):
    """Single attempt to create an ICW IGT Standard record."""
    url = f"{instance}/api/now/table/sn_icw_igt_standard"
    payload = {
        "short_description": title,
        "detailed_description": "<p>Uploading content...</p>",
        "state": "1",           # draft
        "active": "true",
        "cmdb_assignment_type": assignment_type,
    }
    response = requests.post(
        url, auth=(username, password), headers=_HEADERS_JSON, json=payload, timeout=60,
    )
    if response.status_code in (200, 201):
        result = response.json().get("result", {})
        return result.get("sys_id", ""), result.get("number", "")
    return None, response.text


def create_igt_standard(instance, username, password, title, assignment_type="equipment"):
    """Create a draft ICW IGT Standard with retry. Returns (sys_id, number)."""
    return retry_on_failure(
        _create_igt_standard_once,
        instance, username, password, title, assignment_type,
        description="IGT standard creation",
    )


def _update_igt_standard_once(instance, username, password, sys_id, html):
    """Single attempt to update an IGT Standard's detailed_description."""
    url = f"{instance}/api/now/table/sn_icw_igt_standard/{sys_id}"
    response = requests.patch(
        url, auth=(username, password), headers=_HEADERS_JSON,
        json={"detailed_description": html}, timeout=60,
    )
    return response.status_code in (200, 201)


def update_igt_standard(instance, username, password, sys_id, html):
    """Update the IGT Standard HTML content with retry."""
    return retry_on_failure(
        _update_igt_standard_once,
        instance, username, password, sys_id, html,
        description="IGT standard update",
    )


def _create_igt_step_once(instance, username, password, standard_sys_id, title, instructions, order):
    """Single attempt to create one IGT step (sn_icw_std_task)."""
    url = f"{instance}/api/now/table/sn_icw_std_task"
    payload = {
        "standard":          standard_sys_id,
        "short_description": title,
        # 'description' and 'order' inherit from the task base class;
        # field names may vary — adjust if the ICW instance uses different names.
        "description":       instructions,
        "order":             str(order),
    }
    response = requests.post(
        url, auth=(username, password), headers=_HEADERS_JSON, json=payload, timeout=30,
    )
    if response.status_code in (200, 201):
        result = response.json().get("result", {})
        return result.get("sys_id", ""), result.get("number", "")
    return None, response.text


def create_igt_step(instance, username, password, standard_sys_id, title, instructions, order):
    """Create one IGT step record with retry. Returns (sys_id, number)."""
    return retry_on_failure(
        _create_igt_step_once,
        instance, username, password, standard_sys_id, title, instructions, order,
        description=f"IGT step creation (order {order})",
    )
