# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.file.file import has_permission

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.relay import generate_presigned_url


@frappe.whitelist(allow_guest=True)
def serve_file(fid: str):
	file_doc = frappe.get_doc("File", fid)

	if not has_permission(file_doc, "read"):
		frappe.throw(_("You do not have permission to access this file"), frappe.PermissionError)

	if file_doc.get("storage_backend") != STORAGE_BACKEND_S3 or not file_doc.get("cloud_storage_key"):
		frappe.throw(_("File is not stored in S3"))

	url = generate_presigned_url(file_doc.cloud_storage_key)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = url
