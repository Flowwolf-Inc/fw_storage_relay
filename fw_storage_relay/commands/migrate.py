# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import traceback

import click
import frappe
from frappe.commands import get_site, pass_context
from frappe.query_builder import Order
from frappe.query_builder.functions import IfNull

from fw_storage_relay.config import can_offload_file, get_excluded_doctypes
from fw_storage_relay.relay import _copy_s3_metadata_from_duplicate, offload_file, validate_relay_ready

MISSING_LOCAL_FILE_ERROR = "Local file not found on disk"


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
		files = _get_pending_files(current_batch_size, get_excluded_doctypes())
		if not files:
			break

		for file_name in files:
			try:
				file_doc = frappe.get_doc("File", file_name)
				if not can_offload_file(file_doc):
					continue

				if not file_doc.exists_on_disk():
					if _copy_s3_metadata_from_duplicate(file_doc, persist=True):
						processed += 1
						click.echo(f"Synced from duplicate: {file_name}")
						continue

					frappe.db.set_value(
						"File",
						file_name,
						{
							"sync_status": "Failed",
							"sync_error": MISSING_LOCAL_FILE_ERROR,
						},
						update_modified=False,
					)
					_add_comment(file_name, f"S3 Migration: {MISSING_LOCAL_FILE_ERROR}")
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
				_add_comment(file_name, "S3 Migration failed. See Error Log for details.")
				click.echo(f"Failed: {file_name} (logged)")

		frappe.db.commit()

	click.echo(f"Migration complete. Processed {processed} file(s).")


def _get_pending_files(batch_size: int, excluded_doctypes: frozenset[str]) -> list[str]:
	File = frappe.qb.DocType("File")

	query = (
		frappe.qb.from_(File)
		.select(File.name)
		.where(IfNull(File.sync_status, "Pending") == "Pending")
		.where(IfNull(File.storage_backend, "Local") == "Local")
		.where(File.is_folder == 0)
		.where(IfNull(File.file_url, "").not_like("http%"))
		.orderby(File.creation, order=Order.asc)
		.limit(batch_size)
	)

	if excluded_doctypes:
		query = query.where(
			IfNull(File.attached_to_doctype, "").notin(list(excluded_doctypes))
		)

	return query.run(pluck=True)


def _add_comment(file_name: str, message: str) -> None:
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Comment",
			"reference_doctype": "File",
			"reference_name": file_name,
			"content": message,
		}
	).insert(ignore_permissions=True)
