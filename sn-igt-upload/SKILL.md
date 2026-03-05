# Skill: sn-igt-upload

Upload documents to ServiceNow ICW as Industrial Guided Task (IGT) Standards.

## Usage
`/sn-igt-upload <folder-path>`

## What it does
1. Reads all supported files from `<folder-path>`
2. Extracts HTML content from each document
3. Parses ETAPE | METHODE procedure tables (DOCX) or row data (Excel) as IGT steps
4. Creates `sn_icw_igt_standard` records in ServiceNow
5. Uploads embedded images as SN attachments
6. Creates `sn_icw_std_task` step records linked to each standard

## Trigger conditions (via upload_all.py)
- Folder name contains "igt" (case-insensitive), e.g. "IGT docs", "igt_procedures"
- `--igt` flag passed to upload_all.py

## Allowed Tools
- Bash: python *
- Bash: pip *
- Read
- Glob

## Config
```yaml
name: sn-igt-upload
argument: folder-path
disableModelInvocation: true
userInvokable: true
```
