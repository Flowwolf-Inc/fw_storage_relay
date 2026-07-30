# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import os

import frappe
from frappe.utils import get_site_path


@frappe.whitelist()
def get_storage_stats() -> dict:
	"""Return sync status counts and local folder file counts for the storage dashboard."""
	sync_counts = _get_sync_status_counts()
	folder_counts = _get_local_folder_counts()

	return {
		"synced": sync_counts.get("Synced", 0),
		"failed": sync_counts.get("Failed", 0),
		"pending": sync_counts.get("Pending", 0),
		"total": sum(sync_counts.values()),
		"local": {
			"private": folder_counts["private"],
			"public": folder_counts["public"],
			"backup": folder_counts["backup"],
		},
	}


def _get_sync_status_counts() -> dict[str, int]:
	rows = frappe.db.get_all(
		"File",
		fields=["ifnull(`sync_status`, 'Pending') as sync_status", "count(*) as count"],
		group_by="sync_status",
	)
	result: dict[str, int] = {"Synced": 0, "Failed": 0, "Pending": 0}
	for row in rows:
		status = row.sync_status or "Pending"
		result[status] = result.get(status, 0) + int(row.count)
	return result


def _count_files_in_dir(path: str) -> int:
	"""Count regular files in a directory, returning 0 if the directory does not exist."""
	if not os.path.isdir(path):
		return 0
	try:
		return sum(1 for entry in os.scandir(path) if entry.is_file())
	except OSError:
		return 0


def _get_local_folder_counts() -> dict[str, int]:
	return {
		"private": _count_files_in_dir(get_site_path("private", "files")),
		"public": _count_files_in_dir(get_site_path("public", "files")),
		"backup": _count_files_in_dir(get_site_path("private", "backups")),
	}
