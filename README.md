# FW Storage Relay

**FW Storage Relay** moves Frappe file attachments to AWS S3 on upload, frees up local disk, and keeps files accessible through Frappe like nothing changed.

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench --site <site> install-app fw_storage_relay
bench --site <site> migrate
```

## DevOps configuration (`site_config.json`)

AWS credentials are stored at the server level and are not exposed in the Frappe UI or database.

Add these keys to the site's `site_config.json`:

```json
{
  "fw_s3_access_key": "YOUR_ACCESS_KEY",
  "fw_s3_secret_key": "YOUR_SECRET_KEY",
  "fw_s3_region": "ap-south-1",
  "fw_s3_bucket": "your-bucket-name"
}
```

Required IAM permissions on the bucket/prefix:

- `s3:PutObject`
- `s3:GetObject`
- `s3:DeleteObject`

Restart the bench after updating `site_config.json`.

## Admin configuration

Open **FW S3 Relay Settings** (System Manager only):

| Field | Purpose |
|-------|---------|
| Enabled | Master on/off switch for all S3 activity |
| S3 Folder Prefix | Optional subdirectory inside the bucket (default: empty) |
| Make Files Public | Permanent public S3 URLs vs permission-checked presigned URLs |
| Presigned URL Expiry | Seconds before presigned links expire (default: 3600) |
| Excluded Doctypes | Attachments on these doctypes stay on local disk |

## File visibility modes

**Make Files Public = ON**

- Files receive a permanent public S3 HTTPS URL.
- Objects are uploaded with `public-read` ACL.

**Make Files Public = OFF**

- Files are served via `/api/method/fw_storage_relay.api.serve_file.serve_file?fid=<file_id>`.
- Frappe checks file permissions, then redirects to a fresh presigned S3 URL.

## Bench commands

The app ships four bench commands:

| Command | Purpose |
|---------|---------|
| `migrate-s3-files` | Migrate existing local attachments to S3 (see [Bulk migration](#bulk-migration)) |
| `cleanup-s3-orphans` | Delete orphaned local disk files after S3 offload (see [Cleanup orphaned local files](#cleanup-orphaned-local-files)) |
| `update-s3-file-urls` | Rewrite `File.file_url` after a site domain change (see [Site domain migration](#site-domain-migration)) |
| `rename-s3-folder` | Move S3 objects to a new site prefix after a domain change (see [Site domain migration](#site-domain-migration)) |

## Bulk migration

Migrate existing local attachments to S3 (safe to re-run; already-synced files are skipped):

```bash
bench --site <site> migrate-s3-files --batch-size 50
```

Options:

- `--batch-size` — files processed per DB commit batch (default: 50)
- `--limit` — maximum files to process in this run (default: 0 = no limit)
- `--workers` — number of parallel upload threads (default: 1)

For large datasets (multi-TB), run inside `tmux` or `screen` and tune batch size as needed.

## Cleanup orphaned local files

`cleanup-s3-orphans` deletes local disk files that are no longer needed after S3 offload. It has two modes:

- **Default (DB-first)** — finds File records with `sync_status = Synced` and `storage_backend = S3` and removes their leftover local files under `public/files` / `private/files`.
- **`--scan-disk` (disk-first)** — walks `public/files` and `private/files` and deletes any file that has no corresponding File doctype record in the database.

Always do a dry-run first:

```bash
# Dry-run first
bench --site <site> cleanup-s3-orphans --dry-run

# Apply
bench --site <site> cleanup-s3-orphans --workers 4

# Disk-first mode: delete files with no DB record
bench --site <site> cleanup-s3-orphans --scan-disk --dry-run
```

Options:

- `--batch-size` — files per batch (default: 100)
- `--limit` — maximum files to process (default: 0 = no limit)
- `--workers` — parallel deletion threads (default: 1)
- `--dry-run` — report what would be deleted without touching disk
- `--scan-disk` — disk-first orphan scan

Errors are logged to Frappe Error Log. The command never modifies DB records and is safe to re-run.

## Behavior summary

- New uploads on non-excluded doctypes are offloaded to S3 immediately when the relay is enabled.
- Local files are deleted only after a confirmed successful S3 upload.
- Failed uploads keep the local file, log to Frappe Error Log, and set `Sync Error` on the File record.
- Disabling the master toggle stops all S3 activity instantly.

## Site domain migration

When you move a site to a new domain (e.g. from `fortfreight.apps.sandbox.flowwolf.link` to `sandbox-fortfreight.flowwolf.cloud`), two things become stale:

| Field | Why it breaks |
|-------|--------------|
| `File.file_url` | Stored as an absolute URL containing the old domain — private file links will 404 on the new domain |
| `File.cloud_storage_key` | Contains the old site name as an S3 folder prefix — new uploads will land under a different prefix, leaving existing objects under the old one |

> **Public files** (`Make Files Public = ON`) store a direct S3 HTTPS URL that contains no site domain. They are unaffected by either command below.

### Step 1 — Update file URLs (required)

Run this immediately after the site is live on the new domain. It rewrites `File.file_url` for every S3-backed private file so that links point to the new domain.

Always do a dry-run first:

```bash
bench --site <new-site> update-s3-file-urls \
  --old-url https://fortfreight.apps.sandbox.flowwolf.link \
  --new-url https://sandbox-fortfreight.flowwolf.cloud \
  --dry-run
```

Apply when satisfied:

```bash
bench --site <new-site> update-s3-file-urls \
  --old-url https://fortfreight.apps.sandbox.flowwolf.link \
  --new-url https://sandbox-fortfreight.flowwolf.cloud
```

Options:

- `--old-url` — base URL of the old site (trailing slash is stripped automatically)
- `--new-url` — base URL of the new site
- `--batch-size` — records per DB commit (default: 50)
- `--dry-run` — print what would change without writing

### Step 2 — Rename S3 folder (optional)

Without this step, existing S3 objects remain under the old site prefix (e.g. `fortfreight.apps.sandbox.flowwolf.link/private/...`). They are still fully accessible — `serve_file` uses the stored `cloud_storage_key` directly. This command is only needed if you want the bucket layout to reflect the new site name.

For each file it: copies the S3 object to the new key, updates `File.cloud_storage_key` in the database, then deletes the old object.

```bash
# Dry-run first
bench --site <new-site> rename-s3-folder \
  --old-site fortfreight.apps.sandbox.flowwolf.link \
  --new-site sandbox-fortfreight.flowwolf.cloud \
  --dry-run

# Apply
bench --site <new-site> rename-s3-folder \
  --old-site fortfreight.apps.sandbox.flowwolf.link \
  --new-site sandbox-fortfreight.flowwolf.cloud
```

Options:

- `--old-site` — site folder name on the old server (the S3 prefix to rename from)
- `--new-site` — site folder name on the new server (the S3 prefix to rename to)
- `--batch-size` — objects per S3+DB batch (default: 50)
- `--dry-run` — print what would move without touching S3 or the database

> **IAM requirement:** this command calls `s3:CopyObject`. Add it to your bucket policy alongside the existing `s3:PutObject`, `s3:GetObject`, and `s3:DeleteObject`.

Any failures are logged to Frappe Error Log and printed to the console. The command is safe to re-run — successfully renamed objects no longer match the old prefix filter.

### Recommended order

1. Move the site and update DNS / `site_config.json` on the new server.
2. Run `update-s3-file-urls` — fixes broken private file links with no S3 API calls.
3. Optionally run `rename-s3-folder` — reorganises the S3 bucket layout.
4. New uploads after migration will automatically use the new site name as the S3 key prefix.

---

## Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/fw_storage_relay
pre-commit install
```

## License

MIT
