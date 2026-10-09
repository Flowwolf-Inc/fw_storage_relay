# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils import cint

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.relay import (
	get_relay_source_file,
	get_serve_file_url,
	is_synced_s3_source,
	parse_serve_file_fid,
)

BATCH_SIZE = 100
SERVE_URL_LIKE = "%fw_storage_relay.api.serve_file.serve_file%fid=%"


def execute():
	file_table = frappe.qb.DocType("File")
	rows = (
		frappe.qb.from_(file_table)
		.select(file_table.name, file_table.file_url, file_table.content_hash, file_table.old_file_url)
		.where(IfNull(file_table.storage_backend, "Local") == "Local")
		.where(file_table.is_folder == 0)
		.where(file_table.file_url.like(SERVE_URL_LIKE))
	).run(as_dict=True)

	if not rows:
		return

	updated = 0
	for row in rows:
		_link_or_fail(row)
		updated += 1
		if updated % BATCH_SIZE == 0:
			frappe.db.commit()

	frappe.db.commit()


def _link_or_fail(row) -> None:
	source = get_relay_source_file(row.file_url)
	if not source or source.name == row.name or not is_synced_s3_source(source):
		fid = (source.name if source else parse_serve_file_fid(row.file_url)) or "unknown"
		frappe.db.set_value(
			"File",
			row.name,
			{
				"sync_status": "Failed",
				"sync_error": f"Serve URL source {fid} not synced",
			},
			update_modified=False,
		)
		return

	values = {
		"is_private": cint(source.is_private),
		"storage_backend": STORAGE_BACKEND_S3,
		"cloud_storage_key": source.cloud_storage_key,
		"sync_status": "Synced",
		"synced_on": source.synced_on,
		"sync_error": None,
		"file_url": get_serve_file_url(row.name),
	}
	if source.content_hash and not row.content_hash:
		values["content_hash"] = source.content_hash
	if source.old_file_url and not row.old_file_url:
		values["old_file_url"] = source.old_file_url

	frappe.db.set_value("File", row.name, values, update_modified=False)
