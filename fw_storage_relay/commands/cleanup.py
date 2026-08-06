# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Generator

import click
import frappe
from frappe.commands import get_site, pass_context
from frappe.query_builder import Order
from frappe.utils import get_site_path

from fw_storage_relay.config import STORAGE_BACKEND_S3


@dataclass
class _CleanupResult:
	file_name: str
	deleted: bool = False
	already_gone: bool = False
	dry_run: bool = False
	error: str | None = None
	tb: str | None = field(default=None, repr=False)


@dataclass
class _DiskBatchResult:
	deleted: int = 0
	skipped: int = 0
	errors: int = 0


@click.command("cleanup-s3-orphans")
@click.option("--batch-size", default=100, show_default=True, help="Number of files per batch")
@click.option("--limit", default=0, show_default=True, help="Maximum files to process (0 = no limit)")
@click.option("--workers", default=1, show_default=True, help="Number of parallel deletion threads")
@click.option("--dry-run", is_flag=True, default=False, help="Report what would be deleted without touching disk")
@click.option(
	"--scan-disk",
	is_flag=True,
	default=False,
	help=(
		"Disk-first mode: scan public/files and private/files, delete any file that has "
		"no corresponding File doctype record in the DB (orphaned disk files)."
	),
)
@pass_context
def cleanup_s3_orphans(context, batch_size, limit, workers, dry_run, scan_disk):
	"Delete orphaned local disk files — either Synced-to-S3 records still on disk, or files with no DB record (--scan-disk)"

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		if dry_run:
			click.echo("Dry-run mode — no files will be deleted.")

		if scan_disk:
			click.echo("Disk-first mode: scanning local file directories for orphaned files.")
			_run_disk_scan(site=site, batch_size=batch_size, limit=limit, workers=workers, dry_run=dry_run)
		else:
			_run_cleanup(batch_size=batch_size, limit=limit, workers=workers, dry_run=dry_run)
	finally:
		frappe.destroy()


# ---------------------------------------------------------------------------
# DB-first mode (original behaviour)
# ---------------------------------------------------------------------------

def _run_cleanup(batch_size: int, limit: int, workers: int, dry_run: bool):
	site = frappe.local.site

	if workers > 1:
		click.echo(f"Starting parallel cleanup with {workers} worker(s).")
		_run_cleanup_parallel(site=site, batch_size=batch_size, limit=limit, workers=workers, dry_run=dry_run)
	else:
		_run_cleanup_serial(batch_size=batch_size, limit=limit, dry_run=dry_run)


def _get_orphan_local_path(file_name: str, is_private: int) -> str | None:
	"""
	Build the expected original local disk path from file_name and privacy flag.

	After offloading, file_url is updated to the S3 URL, so we cannot use it to
	find the original local file. We reconstruct the path from file_name + is_private.
	"""
	if not file_name:
		return None
	if is_private:
		return get_site_path("private", "files", file_name)
	return get_site_path("public", "files", file_name)


def _process_file(site: str, row: dict, *, dry_run: bool) -> _CleanupResult:
	"""Run in a worker thread — each thread owns its own Frappe DB connection."""
	frappe.init(site=site)
	frappe.connect()
	try:
		local_path = _get_orphan_local_path(row["file_name"], row["is_private"])

		if not local_path or not os.path.exists(local_path):
			return _CleanupResult(file_name=row["name"], already_gone=True, dry_run=dry_run)

		if not dry_run:
			os.remove(local_path)

		return _CleanupResult(file_name=row["name"], deleted=True, dry_run=dry_run)
	except Exception:
		tb = traceback.format_exc()
		try:
			frappe.log_error(
				title="FW Storage Relay Cleanup Failed",
				message=f"File: {row['name']}\n\n{tb}",
			)
		except Exception:
			pass
		return _CleanupResult(file_name=row["name"], error="Cleanup failed. See Error Log.", tb=tb, dry_run=dry_run)
	finally:
		frappe.destroy()


def _run_cleanup_parallel(site: str, batch_size: int, limit: int, workers: int, dry_run: bool):
	deleted = already_gone = errors = 0
	processed = 0
	offset = 0

	with ThreadPoolExecutor(max_workers=workers) as executor:
		while True:
			remaining_limit = None if not limit else max(limit - processed, 0)
			if remaining_limit == 0:
				break

			current_batch_size = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
			rows = _get_synced_files(current_batch_size, offset)
			if not rows:
				break

			futures = {executor.submit(_process_file, site, row, dry_run=dry_run): row for row in rows}
			for future in as_completed(futures):
				result = future.result()
				processed += 1
				if result.error:
					errors += 1
					click.echo(f"Error: {result.file_name} (logged)")
				elif result.already_gone:
					already_gone += 1
				elif result.deleted:
					deleted += 1
					action = "Would delete" if dry_run else "Deleted"
					click.echo(f"{action} [{deleted}]: {result.file_name}")

			# DB records are never modified, so offset must always advance to paginate.
			offset += len(rows)

	_print_summary(deleted=deleted, already_gone=already_gone, errors=errors, dry_run=dry_run)


def _run_cleanup_serial(batch_size: int, limit: int, dry_run: bool):
	deleted = already_gone = errors = 0
	processed = 0
	offset = 0

	while True:
		remaining_limit = None if not limit else max(limit - processed, 0)
		if remaining_limit == 0:
			break

		current_batch_size = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
		rows = _get_synced_files(current_batch_size, offset)
		if not rows:
			break

		for row in rows:
			processed += 1
			try:
				local_path = _get_orphan_local_path(row["file_name"], row["is_private"])

				if not local_path or not os.path.exists(local_path):
					already_gone += 1
					continue

				if not dry_run:
					os.remove(local_path)

				deleted += 1
				action = "Would delete" if dry_run else "Deleted"
				click.echo(f"{action} [{deleted}]: {row['name']}")
			except Exception:
				errors += 1
				frappe.log_error(
					title="FW Storage Relay Cleanup Failed",
					message=f"File: {row['name']}\n\n{traceback.format_exc()}",
				)
				click.echo(f"Error: {row['name']} (logged)")

		# DB records are never modified, so offset must always advance to paginate.
		offset += len(rows)

	_print_summary(deleted=deleted, already_gone=already_gone, errors=errors, dry_run=dry_run)


def _get_synced_files(batch_size: int, offset: int = 0) -> list[dict]:
	File = frappe.qb.DocType("File")

	return (
		frappe.qb.from_(File)
		.select(File.name, File.file_name, File.is_private)
		.where(File.sync_status == "Synced")
		.where(File.storage_backend == STORAGE_BACKEND_S3)
		.where(File.is_folder == 0)
		.where(File.file_name.notnull())
		.orderby(File.creation, order=Order.asc)
		.limit(batch_size)
		.offset(offset)
		.run(as_dict=True)
	)


# ---------------------------------------------------------------------------
# Disk-first mode (--scan-disk)
# ---------------------------------------------------------------------------

def _iter_disk_batches(
	batch_size: int, limit: int
) -> Generator[tuple[list[str], list[str]], None, None]:
	"""
	Walk public/files and private/files and yield (public_paths, private_paths) batches.

	Each yielded batch contains at most batch_size entries total.
	Yields tuples of (abs_paths, file_names) so callers can delete by path without
	needing to reconstruct it.
	"""
	dirs = [
		get_site_path("public", "files"),
		get_site_path("private", "files"),
	]

	batch_paths: list[str] = []
	batch_names: list[str] = []
	total = 0

	for directory in dirs:
		if not os.path.isdir(directory):
			continue
		for dirpath, _, filenames in os.walk(directory):
			for fname in filenames:
				if limit and total >= limit:
					if batch_paths:
						yield batch_paths, batch_names
					return

				abs_path = os.path.join(dirpath, fname)
				batch_paths.append(abs_path)
				batch_names.append(fname)
				total += 1

				if len(batch_paths) >= batch_size:
					yield batch_paths, batch_names
					batch_paths = []
					batch_names = []

	if batch_paths:
		yield batch_paths, batch_names


def _process_disk_batch(
	site: str,
	abs_paths: list[str],
	file_names: list[str],
	*,
	dry_run: bool,
) -> _DiskBatchResult:
	"""
	Worker function: given a batch of disk files, query DB for any that have a
	File doctype record, then delete the rest (orphans).
	Each worker thread owns its own Frappe DB connection.
	"""
	frappe.init(site=site)
	frappe.connect()
	result = _DiskBatchResult()
	try:
		File = frappe.qb.DocType("File")
		found_in_db = set(
			frappe.qb.from_(File)
			.select(File.file_name)
			.where(File.file_name.isin(file_names))
			.run(pluck=True)
		)

		for abs_path, fname in zip(abs_paths, file_names):
			if fname in found_in_db:
				result.skipped += 1
				continue
			try:
				if not dry_run:
					os.remove(abs_path)
				result.deleted += 1
			except Exception:
				result.errors += 1
				try:
					frappe.log_error(
						title="FW Storage Relay Disk Cleanup Failed",
						message=f"Path: {abs_path}\n\n{traceback.format_exc()}",
					)
				except Exception:
					pass
	except Exception:
		result.errors += len(abs_paths)
		try:
			frappe.log_error(
				title="FW Storage Relay Disk Cleanup Batch Failed",
				message=traceback.format_exc(),
			)
		except Exception:
			pass
	finally:
		frappe.destroy()

	return result


def _run_disk_scan(site: str, batch_size: int, limit: int, workers: int, dry_run: bool):
	deleted = skipped = errors = 0
	action = "Would delete" if dry_run else "Deleted"

	if workers > 1:
		click.echo(f"Starting parallel disk scan with {workers} worker(s).")
		with ThreadPoolExecutor(max_workers=workers) as executor:
			futures = {}
			for abs_paths, file_names in _iter_disk_batches(batch_size, limit):
				f = executor.submit(_process_disk_batch, site, abs_paths, file_names, dry_run=dry_run)
				futures[f] = len(abs_paths)

			for future in as_completed(futures):
				res = future.result()
				deleted += res.deleted
				skipped += res.skipped
				errors += res.errors
				if res.deleted:
					click.echo(f"{action}: {res.deleted} file(s) in batch | Total so far: {deleted}")
	else:
		for abs_paths, file_names in _iter_disk_batches(batch_size, limit):
			# In serial mode run in main thread (frappe context already initialised).
			File = frappe.qb.DocType("File")
			found_in_db = set(
				frappe.qb.from_(File)
				.select(File.file_name)
				.where(File.file_name.isin(file_names))
				.run(pluck=True)
			)

			for abs_path, fname in zip(abs_paths, file_names):
				if fname in found_in_db:
					skipped += 1
					continue
				try:
					if not dry_run:
						os.remove(abs_path)
					deleted += 1
					click.echo(f"{action} [{deleted}]: {abs_path}")
				except Exception:
					errors += 1
					frappe.log_error(
						title="FW Storage Relay Disk Cleanup Failed",
						message=f"Path: {abs_path}\n\n{traceback.format_exc()}",
					)
					click.echo(f"Error: {abs_path} (logged)")

	_print_summary(deleted=deleted, already_gone=skipped, errors=errors, dry_run=dry_run)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _print_summary(*, deleted: int, already_gone: int, errors: int, dry_run: bool):
	action = "Would delete" if dry_run else "Deleted"
	click.echo(
		f"\nCleanup complete. {action}: {deleted} | Has DB record (skipped): {already_gone} | Errors: {errors}"
	)
