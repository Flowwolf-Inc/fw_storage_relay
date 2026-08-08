# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe


def after_install():
	ensure_settings()


def after_migrate():
	ensure_settings()
	remove_obsolete_custom_fields()
	ensure_indexes()


def ensure_indexes():
	# Duplicate detection and propagation filter tabFile by content_hash,
	# which is unindexed by default and full-scans on large sites.
	frappe.db.add_index("File", ["content_hash"])


def remove_obsolete_custom_fields():
	# The trailing "Details" tab break became obsolete once the Cloud Storage
	# tab was moved to the end of the File form. Fixture sync does not delete
	# records removed from the fixture file, so clean it up here.
	if frappe.db.exists("Custom Field", "File-file_details_tab"):
		frappe.delete_doc("Custom Field", "File-file_details_tab", ignore_permissions=True, force=True)
		frappe.db.commit()


def ensure_settings():
	if frappe.db.exists("FW S3 Relay Settings", "FW S3 Relay Settings"):
		return

	doc = frappe.get_doc(
		{
			"doctype": "FW S3 Relay Settings",
			"enabled": 0,
			"s3_folder_prefix": "",
			"presigned_url_expiry": 3600,
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
