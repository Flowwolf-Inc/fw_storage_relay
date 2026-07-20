# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from fw_storage_relay.share_key import (
	generate_file_share_key as _generate_file_share_key,
	get_file_share_info as _get_file_share_info,
	regenerate_file_share_key as _regenerate_file_share_key,
	reset_file_share_key as _reset_file_share_key,
	revoke_file_share_key as _revoke_file_share_key,
)


@frappe.whitelist()
def get_file_share_info(file_name: str):
	_require_file_read_permission(file_name)
	return _get_file_share_info(file_name)


@frappe.whitelist()
def generate_file_share_key(file_name: str):
	_require_file_write_permission(file_name)
	result = _generate_file_share_key(file_name)
	frappe.db.commit()
	return result


@frappe.whitelist()
def reset_file_share_key(file_name: str):
	_require_file_write_permission(file_name)
	result = _reset_file_share_key(file_name)
	frappe.db.commit()
	return result


@frappe.whitelist()
def regenerate_file_share_key(file_name: str):
	_require_file_write_permission(file_name)
	result = _regenerate_file_share_key(file_name)
	frappe.db.commit()
	return result


@frappe.whitelist()
def revoke_file_share_key(file_name: str):
	_require_file_write_permission(file_name)
	result = _revoke_file_share_key(file_name)
	frappe.db.commit()
	return result


def _require_file_read_permission(file_name: str):
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.has_permission("read"):
		frappe.throw(_("You do not have permission to access this file"), frappe.PermissionError)


def _require_file_write_permission(file_name: str):
	file_doc = frappe.get_doc("File", file_name)
	if not file_doc.has_permission("write"):
		frappe.throw(_("You do not have permission to modify this file"), frappe.PermissionError)
