# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import traceback

import click
import frappe
from frappe.commands import get_site, pass_context

from fw_storage_relay.config import can_offload_file
from fw_storage_relay.relay import offload_file, validate_relay_ready


@click.command("migrate-s3-files")
@click.option("--batch-size", default=50, show_default=True, help="Number of files per batch")
@click.option("--limit", default=0, show_default=True, help="Maximum files to process (0 = no limit)")
@pass_context
def migrate_s3_files(context, batch_size, limit):
	"Migrate local File attachments to S3"

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		_run_migration(batch_size=batch_size, limit=limit)
	finally:
		frappe.destroy()


def _run_migration(batch_size: int, limit: int):
	if not validate_relay_ready():
		click.echo("FW Storage Relay is disabled or S3 site_config is missing.")
		return

	processed = 0

	while True:
		remaining_limit = None if not limit else max(limit - processed, 0)
		if remaining_limit == 0:
			break

		current_batch_size = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
		files = _get_pending_files(current_batch_size)
		if not files:
			break

		for file_name in files:
			try:
				file_doc = frappe.get_doc("File", file_name)
				if not can_offload_file(file_doc):
					continue

				if not file_doc.exists_on_disk():
					click.echo(f"Skipping missing local file: {file_name}")
					continue

				offload_file(file_doc, persist=True)
				processed += 1
				click.echo(f"Migrated {processed}: {file_name}")
			except Exception:
				frappe.log_error(
					title="FW Storage Relay Migration Failed",
					message=f"File: {file_name}\n\n{traceback.format_exc()}",
				)
				frappe.db.set_value(
					"File",
					file_name,
					{
						"sync_status": "Failed",
						"sync_error": "Migration failed. See Error Log.",
					},
					update_modified=False,
				)
				click.echo(f"Failed: {file_name} (logged)")

		frappe.db.commit()

	click.echo(f"Migration complete. Processed {processed} file(s).")


def _get_pending_files(batch_size: int) -> list[str]:
	return frappe.db.sql(
		"""
		SELECT name
		FROM `tabFile`
		WHERE IFNULL(sync_status, 'Pending') != 'Synced'
			AND IFNULL(storage_backend, 'Local') = 'Local'
			AND is_folder = 0
			AND IFNULL(file_url, '') NOT LIKE 'http%%'
		ORDER BY creation
		LIMIT %s
		""",
		batch_size,
		pluck=True,
	)
