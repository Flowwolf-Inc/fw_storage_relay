# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from fw_storage_relay.relay import manual_offload_file


@frappe.whitelist()
def offload_to_s3(file_name: str):
	file_doc = frappe.get_doc("File", file_name)

	if not file_doc.has_permission("write"):
		frappe.throw(_("You do not have permission to modify this file"), frappe.PermissionError)

	result = manual_offload_file(file_doc)
	frappe.db.commit()
	return result
