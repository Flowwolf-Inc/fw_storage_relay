# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

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
@click.option("--workers", default=1, show_default=True, help="Number of parallel upload threads")
@pass_context
def migrate_s3_files(context, batch_size, limit, workers):
	"Migrate local File attachments to S3"

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		_run_migration(batch_size=batch_size, limit=limit, workers=workers)
	finally:
		frappe.destroy()


@dataclass
class _FileResult:
	file_name: str
	success: bool
	synced_from_duplicate: bool = False
	missing: bool = False
	error: str | None = None
	tb: str | None = None


def _process_file(site: str, file_name: str) -> _FileResult:
	"""Run in a worker thread — each thread owns its own Frappe DB connection."""
	frappe.init(site=site)
	frappe.connect()
	try:
		file_doc = frappe.get_doc("File", file_name)
		if not can_offload_file(file_doc):
			return _FileResult(file_name=file_name, success=False)

		if not file_doc.exists_on_disk():
			if _copy_s3_metadata_from_duplicate(file_doc, persist=True):
				frappe.db.commit()
				return _FileResult(file_name=file_name, success=True, synced_from_duplicate=True)

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
			frappe.db.commit()
			return _FileResult(file_name=file_name, success=False, missing=True)

		offload_file(file_doc, persist=True)
		frappe.db.commit()
		return _FileResult(file_name=file_name, success=True)
	except Exception:
		tb = traceback.format_exc()
		error_msg = "Migration failed. See Error Log."
		try:
			frappe.log_error(
				title="FW Storage Relay Migration Failed",
				message=f"File: {file_name}\n\n{tb}",
			)
			frappe.db.set_value(
				"File",
				file_name,
				{
					"sync_status": "Failed",
					"sync_error": error_msg,
				},
				update_modified=False,
			)
			_add_comment(file_name, "S3 Migration failed. See Error Log for details.")
			frappe.db.commit()
		except Exception:
			pass
		return _FileResult(file_name=file_name, success=False, error=error_msg, tb=tb)
	finally:
		frappe.destroy()


def _run_migration(batch_size: int, limit: int, workers: int = 1):
	if not validate_relay_ready():
		click.echo("FW Storage Relay is disabled or S3 site_config is missing.")
		return

	site = frappe.local.site

	if workers > 1:
		click.echo(f"Starting parallel migration with {workers} worker(s).")
		_run_migration_parallel(site=site, batch_size=batch_size, limit=limit, workers=workers)
	else:
		_run_migration_serial(batch_size=batch_size, limit=limit)


def _run_migration_parallel(site: str, batch_size: int, limit: int, workers: int):
	processed = 0

	with ThreadPoolExecutor(max_workers=workers) as executor:
		while True:
			remaining_limit = None if not limit else max(limit - processed, 0)
			if remaining_limit == 0:
				break

			current_batch_size = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
			files = _get_pending_files(current_batch_size, get_excluded_doctypes())
			if not files:
				break

			futures = {executor.submit(_process_file, site, fn): fn for fn in files}
			for future in as_completed(futures):
				result = future.result()
				if result.synced_from_duplicate:
					processed += 1
					click.echo(f"Synced from duplicate: {result.file_name}")
				elif result.success:
					processed += 1
					click.echo(f"Migrated {processed}: {result.file_name}")
				elif result.missing:
					click.echo(f"Skipping missing local file: {result.file_name}")
				elif result.error:
					click.echo(f"Failed: {result.file_name} (logged)")

	click.echo(f"Migration complete. Processed {processed} file(s).")


def _run_migration_serial(batch_size: int, limit: int):
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
