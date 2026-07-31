# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import re
import traceback

import click
import frappe
from botocore.exceptions import ClientError
from frappe.commands import get_site, pass_context
from frappe.query_builder import Order

from fw_storage_relay.config import get_s3_config
from fw_storage_relay.storage import get_backend


# ---------------------------------------------------------------------------
# Command 1 — update-s3-file-urls
# ---------------------------------------------------------------------------


@click.command("update-s3-file-urls")
@click.option("--old-url", required=True, help="Old site base URL, e.g. https://fortfreight.apps.sandbox.flowwolf.link")
@click.option("--new-url", required=True, help="New site base URL, e.g. https://sandbox-fortfreight.flowwolf.cloud")
@click.option("--batch-size", default=50, show_default=True, help="Number of records per DB commit batch")
@click.option("--dry-run", is_flag=True, help="Preview affected records without writing changes")
@pass_context
def update_s3_file_urls(context, old_url, new_url, batch_size, dry_run):
	"Replace the old site URL in File.file_url for all S3-backed files"

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		_run_url_update(old_url=old_url.rstrip("/"), new_url=new_url.rstrip("/"), batch_size=batch_size, dry_run=dry_run)
	finally:
		frappe.destroy()


def _run_url_update(*, old_url: str, new_url: str, batch_size: int, dry_run: bool):
	# Strip protocol so the LIKE filter matches both http:// and https:// stored values.
	old_host = old_url.split("://", 1)[-1]
	old_url_pattern = re.compile(r"https?://" + re.escape(old_host))

	if dry_run:
		click.echo(f"[dry-run] Scanning for file_url containing host: {old_host!r}")
	else:
		click.echo(f"Updating file_url host {old_host!r} → {new_url!r}")

	File = frappe.qb.DocType("File")
	processed = 0

	while True:
		rows = (
			frappe.qb.from_(File)
			.select(File.name, File.file_url)
			.where(File.storage_backend == "S3")
			.where(File.file_url.like(f"%{old_host}%"))
			.orderby(File.creation, order=Order.asc)
			.limit(batch_size)
		).run(as_dict=True)

		if not rows:
			break

		for row in rows:
			new_file_url = old_url_pattern.sub(new_url, row.file_url, count=1)

			if dry_run:
				click.echo(f"  [dry-run] {row.name}: {row.file_url!r} → {new_file_url!r}")
			else:
				frappe.db.set_value("File", row.name, "file_url", new_file_url, update_modified=False)

			processed += 1

		if not dry_run:
			frappe.db.commit()
			click.echo(f"Updated {processed} record(s) so far...")

	label = "[dry-run] Would update" if dry_run else "Updated"
	click.echo(f"{label} {processed} file_url record(s).")


# ---------------------------------------------------------------------------
# Command 2 — rename-s3-folder
# ---------------------------------------------------------------------------


@click.command("rename-s3-folder")
@click.option("--old-site", required=True, help="Old site folder name, e.g. fortfreight.apps.sandbox.flowwolf.link")
@click.option("--new-site", required=True, help="New site folder name, e.g. sandbox-fortfreight.flowwolf.cloud")
@click.option("--batch-size", default=50, show_default=True, help="Number of distinct S3 keys per commit batch")
@click.option("--dry-run", is_flag=True, help="Preview affected records without touching S3 or the database")
@pass_context
def rename_s3_folder(context, old_site, new_site, batch_size, dry_run):
	"Copy S3 objects from the old site prefix to the new one and update cloud_storage_key in File records"

	site = get_site(context)
	frappe.init(site=site)
	frappe.connect()

	try:
		_run_folder_rename(old_site=old_site, new_site=new_site, batch_size=batch_size, dry_run=dry_run)
	finally:
		frappe.destroy()


def _run_folder_rename(*, old_site: str, new_site: str, batch_size: int, dry_run: bool):
	if not get_s3_config():
		click.echo("S3 configuration is missing from site_config.json. Aborting.")
		return

	if dry_run:
		click.echo(f"[dry-run] Scanning for cloud_storage_key under prefix: {old_site}/")
	else:
		click.echo(f"Renaming S3 folder: {old_site}/ → {new_site}/")

	backend = get_backend()
	File = frappe.qb.DocType("File")
	processed = 0
	failed = 0
	old_prefix = f"{old_site}/"

	while True:
		# Select DISTINCT keys — multiple File records may share the same cloud_storage_key
		# (duplicate file deduplication). Processing by key avoids CopyObject NoSuchKey errors
		# that occur when a sibling record already deleted the old S3 object.
		keys = (
			frappe.qb.from_(File)
			.select(File.cloud_storage_key)
			.distinct()
			.where(File.storage_backend == "S3")
			.where(File.cloud_storage_key.like(f"{old_prefix}%"))
			.orderby(File.cloud_storage_key, order=Order.asc)
			.limit(batch_size)
		).run(pluck="cloud_storage_key")

		if not keys:
			break

		for old_key in keys:
			new_key = new_site + old_key[len(old_site):]

			if dry_run:
				click.echo(f"  [dry-run] {old_key!r} → {new_key!r}")
				processed += 1
				continue

			just_copied = False
			try:
				backend._client.copy_object(
					CopySource={"Bucket": backend.bucket, "Key": old_key},
					Bucket=backend.bucket,
					Key=new_key,
				)
				just_copied = True
			except ClientError as exc:
				error_code = exc.response["Error"]["Code"]
				if error_code == "NoSuchKey":
					# Old key may have been deleted by a previous partial run.
					# If the new key already exists the S3 rename is done; only fix the DB.
					if backend.exists(new_key):
						click.echo(f"Already renamed in S3, fixing DB only: {old_key!r}")
					else:
						failed += 1
						frappe.log_error(
							title="FW Storage Relay S3 Folder Rename Failed",
							message=f"Key: {old_key}\n\n{traceback.format_exc()}",
						)
						click.echo(f"Failed (key missing in S3): {old_key!r} — see Error Log")
						continue
				else:
					failed += 1
					frappe.log_error(
						title="FW Storage Relay S3 Folder Rename Failed",
						message=f"Key: {old_key}\n\n{traceback.format_exc()}",
					)
					click.echo(f"Failed: {old_key!r} — see Error Log")
					continue

			# Bulk-update ALL File records that share this old key in a single query.
			(
				frappe.qb.update(File)
				.set(File.cloud_storage_key, new_key)
				.where(File.cloud_storage_key == old_key)
			).run()

			# Only delete the old S3 object if we copied it in this run.
			if just_copied:
				try:
					backend.delete(old_key)
				except ClientError:
					frappe.log_error(
						title="FW Storage Relay S3 Delete Failed After Rename",
						message=f"Key: {old_key}\n\n{traceback.format_exc()}",
					)
					click.echo(f"Warning: copied but failed to delete old key {old_key!r} — see Error Log")

			processed += 1
			click.echo(f"Renamed {processed}: {old_key!r} → {new_key!r}")

		if not dry_run:
			frappe.db.commit()

	label = "[dry-run] Would rename" if dry_run else "Renamed"
	click.echo(f"{label} {processed} S3 key(s).")
	if failed:
		click.echo(f"Failures: {failed} — check Frappe Error Log for details.")
