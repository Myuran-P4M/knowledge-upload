"use strict";

const express = require("express");
const { execSync } = require("child_process");
const os = require("os");
const fs = require("fs");
const path = require("path");
const https = require("https");
const http = require("http");
require("dotenv").config();

const app = express();
app.use(express.json());

const AUTH_TOKEN = process.env.MCP_AUTH_TOKEN;
const PROJECT_ROOT = process.env.PROJECT_ROOT || "/project";
const PORT = parseInt(process.env.PORT || "3000", 10);

if (!AUTH_TOKEN) {
  console.error("[FATAL] MCP_AUTH_TOKEN is not set. Exiting.");
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Middleware: Bearer token auth
// ---------------------------------------------------------------------------
function authenticate(req, res, next) {
  const header = req.headers.authorization || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token || token !== AUTH_TOKEN) {
    console.warn(`[AUTH] Rejected request from ${req.ip} — invalid token`);
    return res.status(401).json({ error: "Unauthorized" });
  }
  next();
}

// ---------------------------------------------------------------------------
// Request logger
// ---------------------------------------------------------------------------
app.use((req, _res, next) => {
  console.log(`[${new Date().toISOString()}] ${req.method} ${req.path} — ${req.ip}`);
  next();
});

// ---------------------------------------------------------------------------
// GET /health
// ---------------------------------------------------------------------------
app.get("/health", (_req, res) => {
  res.json({
    status: "ok",
    host: os.hostname(),
    uptime_s: Math.floor(process.uptime()),
    project_root: PROJECT_ROOT,
    timestamp: new Date().toISOString(),
  });
});

// ---------------------------------------------------------------------------
// POST /trigger-igt-upload
// Body: { folder: string, doc_sys_id?: string }
// ---------------------------------------------------------------------------
app.post("/trigger-igt-upload", authenticate, (req, res) => {
  const { folder, doc_sys_id } = req.body;

  if (!folder || typeof folder !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'folder' parameter" });
  }

  // Safety: reject path traversal attempts
  const resolvedFolder = path.resolve(PROJECT_ROOT, folder);
  if (!resolvedFolder.startsWith(path.resolve(PROJECT_ROOT))) {
    return res.status(400).json({ error: "Invalid folder path" });
  }

  const cmd = `cd "${PROJECT_ROOT}" && python3 upload_all.py "${folder}" --igt`;
  console.log(`[IGT] Executing: ${cmd}`);

  try {
    const output = execSync(cmd, {
      encoding: "utf8",
      timeout: 300_000, // 5 minutes
      env: { ...process.env },
    });

    const igtsCreated = output.match(/IGTS\d+/g) || [];
    const sections   = (output.match(/Sections\s*:\s*(\d+)/g) || []).length;
    const questions  = (output.match(/Questions\s*:\s*(\d+)/g) || []).length;
    const photos     = (output.match(/Photos\s*:\s*(\d+)/g) || []).length;
    const errors     = output.match(/ERROR.*/gm) || [];

    console.log(`[IGT] Done — created: ${igtsCreated.join(", ") || "none"}`);

    return res.json({
      success: true,
      igts_created: igtsCreated,
      stats: { sections, questions, photos },
      errors: errors.length ? errors : undefined,
      doc_sys_id: doc_sys_id || null,
      output,
    });
  } catch (err) {
    const stderr = err.stderr ? err.stderr.toString() : "";
    const stdout = err.stdout ? err.stdout.toString() : "";
    console.error("[IGT] Error:", err.message);
    console.error("[IGT] stderr:", stderr);

    return res.status(500).json({
      error: err.message,
      stderr,
      stdout,
      doc_sys_id: doc_sys_id || null,
    });
  }
});

// ---------------------------------------------------------------------------
// POST /trigger-kb-upload
// Body: { folder: string, doc_sys_id?: string }
// ---------------------------------------------------------------------------
app.post("/trigger-kb-upload", authenticate, (req, res) => {
  const { folder, doc_sys_id } = req.body;

  if (!folder || typeof folder !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'folder' parameter" });
  }

  const resolvedFolder = path.resolve(PROJECT_ROOT, folder);
  if (!resolvedFolder.startsWith(path.resolve(PROJECT_ROOT))) {
    return res.status(400).json({ error: "Invalid folder path" });
  }

  const cmd = `cd "${PROJECT_ROOT}" && python3 upload_all.py "${folder}"`;
  console.log(`[KB] Executing: ${cmd}`);

  try {
    const output = execSync(cmd, {
      encoding: "utf8",
      timeout: 300_000,
      env: { ...process.env },
    });

    const articles = (output.match(/KB\d+/g) || []);
    const errors   = output.match(/ERROR.*/gm) || [];

    console.log(`[KB] Done — articles: ${articles.join(", ") || "none"}`);

    return res.json({
      success: true,
      articles_created: articles,
      errors: errors.length ? errors : undefined,
      doc_sys_id: doc_sys_id || null,
      output,
    });
  } catch (err) {
    const stderr = err.stderr ? err.stderr.toString() : "";
    const stdout = err.stdout ? err.stdout.toString() : "";
    console.error("[KB] Error:", err.message);

    return res.status(500).json({
      error: err.message,
      stderr,
      stdout,
      doc_sys_id: doc_sys_id || null,
    });
  }
});

// ---------------------------------------------------------------------------
// Helper: download a ServiceNow attachment to a temp directory
// Returns: { tempDir, filePath, fileName }
// ---------------------------------------------------------------------------
function downloadSnAttachment(attachmentSysId) {
  const snInstance = process.env.SN_INSTANCE.replace(/\/$/, "");
  const snUser     = process.env.SN_USERNAME;
  const snPass     = process.env.SN_PASSWORD;

  // 1. Fetch attachment metadata to get the filename
  const metaUrl = `${snInstance}/api/now/attachment/${attachmentSysId}`;
  const metaRaw = execSync(
    `curl -sf -u "${snUser}:${snPass}" -H "Accept: application/json" "${metaUrl}"`,
    { encoding: "utf8", timeout: 30_000 }
  );
  const meta = JSON.parse(metaRaw);
  const fileName = meta.result.file_name;
  if (!fileName) throw new Error("Could not determine attachment filename from SN metadata");

  // 2. Download the binary into a temp directory
  const tempDir  = fs.mkdtempSync(path.join(os.tmpdir(), "sn-attach-"));
  const filePath = path.join(tempDir, fileName);
  const fileUrl  = `${snInstance}/api/now/attachment/${attachmentSysId}/file`;

  execSync(
    `curl -sf -u "${snUser}:${snPass}" -o "${filePath}" "${fileUrl}"`,
    { timeout: 120_000 }
  );

  console.log(`[ATTACH] Downloaded ${fileName} → ${filePath}`);
  return { tempDir, filePath, fileName };
}

// ---------------------------------------------------------------------------
// POST /trigger-igt-upload-attachment
// Body: { attachment_sys_id: string, doc_sys_id?: string }
// ---------------------------------------------------------------------------
app.post("/trigger-igt-upload-attachment", authenticate, (req, res) => {
  const { attachment_sys_id, doc_sys_id } = req.body;

  if (!attachment_sys_id || typeof attachment_sys_id !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'attachment_sys_id' parameter" });
  }

  let tempDir;
  try {
    const { tempDir: td, fileName } = downloadSnAttachment(attachment_sys_id);
    tempDir = td;

    // tempDir is an absolute path outside PROJECT_ROOT — pass it directly
    const cmd = `python3 "${PROJECT_ROOT}/upload_all.py" "${tempDir}" --igt`;
    console.log(`[IGT-ATTACH] Executing: ${cmd}`);

    const output = execSync(cmd, {
      encoding: "utf8",
      timeout: 300_000,
      env: { ...process.env },
    });

    const igtsCreated = output.match(/IGTS\d+/g) || [];
    const sections    = (output.match(/Sections\s*:\s*(\d+)/g) || []).length;
    const questions   = (output.match(/Questions\s*:\s*(\d+)/g) || []).length;
    const photos      = (output.match(/Photos\s*:\s*(\d+)/g) || []).length;
    const errors      = output.match(/ERROR.*/gm) || [];

    console.log(`[IGT-ATTACH] Done — created: ${igtsCreated.join(", ") || "none"}`);

    return res.json({
      success: true,
      file_name: fileName,
      igts_created: igtsCreated,
      stats: { sections, questions, photos },
      errors: errors.length ? errors : undefined,
      doc_sys_id: doc_sys_id || null,
      output,
    });
  } catch (err) {
    const stderr = err.stderr ? err.stderr.toString() : "";
    const stdout = err.stdout ? err.stdout.toString() : "";
    console.error("[IGT-ATTACH] Error:", err.message);
    return res.status(500).json({ error: err.message, stderr, stdout, doc_sys_id: doc_sys_id || null });
  } finally {
    if (tempDir) {
      try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch (_) {}
      console.log(`[IGT-ATTACH] Cleaned up temp dir ${tempDir}`);
    }
  }
});

// ---------------------------------------------------------------------------
// POST /trigger-kb-upload-attachment
// Body: { attachment_sys_id: string, doc_sys_id?: string }
// ---------------------------------------------------------------------------
app.post("/trigger-kb-upload-attachment", authenticate, (req, res) => {
  const { attachment_sys_id, doc_sys_id } = req.body;

  if (!attachment_sys_id || typeof attachment_sys_id !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'attachment_sys_id' parameter" });
  }

  let tempDir;
  try {
    const { tempDir: td, fileName } = downloadSnAttachment(attachment_sys_id);
    tempDir = td;

    const cmd = `python3 "${PROJECT_ROOT}/upload_all.py" "${tempDir}"`;
    console.log(`[KB-ATTACH] Executing: ${cmd}`);

    const output = execSync(cmd, {
      encoding: "utf8",
      timeout: 300_000,
      env: { ...process.env },
    });

    const articles = output.match(/KB\d+/g) || [];
    const errors   = output.match(/ERROR.*/gm) || [];

    console.log(`[KB-ATTACH] Done — articles: ${articles.join(", ") || "none"}`);

    return res.json({
      success: true,
      file_name: fileName,
      articles_created: articles,
      errors: errors.length ? errors : undefined,
      doc_sys_id: doc_sys_id || null,
      output,
    });
  } catch (err) {
    const stderr = err.stderr ? err.stderr.toString() : "";
    const stdout = err.stdout ? err.stdout.toString() : "";
    console.error("[KB-ATTACH] Error:", err.message);
    return res.status(500).json({ error: err.message, stderr, stdout, doc_sys_id: doc_sys_id || null });
  } finally {
    if (tempDir) {
      try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch (_) {}
      console.log(`[KB-ATTACH] Cleaned up temp dir ${tempDir}`);
    }
  }
});

// ---------------------------------------------------------------------------
// POST /preview-igt-steps  (dry-run — no ServiceNow writes)
// Body: { folder: string }
// ---------------------------------------------------------------------------
app.post("/preview-igt-steps", authenticate, (req, res) => {
  const { folder } = req.body;

  if (!folder || typeof folder !== "string") {
    return res.status(400).json({ error: "Missing or invalid 'folder' parameter" });
  }

  const cmd = `cd "${PROJECT_ROOT}" && python3 sn-igt-skill/extract_steps.py "${folder}"`;
  console.log(`[PREVIEW] Executing: ${cmd}`);

  try {
    const output = execSync(cmd, {
      encoding: "utf8",
      timeout: 60_000,
      env: { ...process.env },
    });

    // extract JSON array from output
    const match = output.match(/(\[[\s\S]*\])/);
    if (!match) {
      return res.status(500).json({ error: "Could not parse extraction output", raw: output });
    }

    return res.json({ success: true, preview: JSON.parse(match[1]) });
  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
});

// ---------------------------------------------------------------------------
// 404 fallback
// ---------------------------------------------------------------------------
app.use((_req, res) => {
  res.status(404).json({ error: "Not found" });
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
app.listen(PORT, "0.0.0.0", () => {
  console.log(`╔══════════════════════════════════════════╗`);
  console.log(`║        SN MCP Bridge — started           ║`);
  console.log(`╠══════════════════════════════════════════╣`);
  console.log(`║  http://0.0.0.0:${PORT}                     ║`);
  console.log(`║  Project root : ${PROJECT_ROOT}`);
  console.log(`║  Host         : ${os.hostname()}`);
  console.log(`╚══════════════════════════════════════════╝`);
});
