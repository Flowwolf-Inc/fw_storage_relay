# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe


def after_install():
	ensure_settings()


def after_migrate():
	ensure_settings()


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
