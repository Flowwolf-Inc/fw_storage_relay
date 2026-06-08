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

## Bulk migration

Migrate existing local attachments to S3 (safe to re-run; already-synced files are skipped):

```bash
bench --site <site> migrate-s3-files --batch-size 50
```

Options:

- `--batch-size` — files processed per DB commit batch (default: 50)
- `--limit` — maximum files to process in this run (default: 0 = no limit)

For large datasets (multi-TB), run inside `tmux` or `screen` and tune batch size as needed.

## Behavior summary

- New uploads on non-excluded doctypes are offloaded to S3 immediately when the relay is enabled.
- Local files are deleted only after a confirmed successful S3 upload.
- Failed uploads keep the local file, log to Frappe Error Log, and set `Sync Error` on the File record.
- Disabling the master toggle stops all S3 activity instantly.

## Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/fw_storage_relay
pre-commit install
```

## License

MIT
