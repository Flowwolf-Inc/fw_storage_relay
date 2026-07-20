# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.file.file import has_permission

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.relay import generate_presigned_url
from fw_storage_relay.share_key import validate_file_share_key


@frappe.whitelist(allow_guest=True)
def serve_file(fid: str, token: str | None = None):
	file_doc = frappe.get_doc("File", fid)

	if file_doc.get("storage_backend") != STORAGE_BACKEND_S3 or not file_doc.get("cloud_storage_key"):
		frappe.throw(_("File is not stored in S3"))

	if frappe.session.user != "Guest":
		if not has_permission(file_doc, "read"):
			frappe.throw(_("You do not have permission to access this file"), frappe.PermissionError)
	elif not _guest_can_access(file_doc, token):
		frappe.throw(_("You do not have permission to access this file"), frappe.PermissionError)

	url = generate_presigned_url(file_doc.cloud_storage_key)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = url


def _guest_can_access(file_doc, token: str | None) -> bool:
	if token and validate_file_share_key(file_doc.name, token):
		return True

	return has_permission(file_doc, "read")
