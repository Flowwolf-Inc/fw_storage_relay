# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.document_share_key.document_share_key import is_expired
from frappe.utils import add_months, get_url, getdate

SHARE_KEY_DOCTYPE = "Document Share Key"
SHARE_KEY_REFERENCE_DOCTYPE = "File"
SHARE_KEY_VALIDITY_MONTHS = 6


def get_share_key_expiry():
	return add_months(getdate(), SHARE_KEY_VALIDITY_MONTHS)


def get_share_link(file_name: str, token: str) -> str:
	return get_url(
		f"/api/method/fw_storage_relay.api.serve_file.serve_file?fid={file_name}&token={token}"
	)


def get_active_share_key(file_name: str) -> dict | None:
	keys = frappe.get_all(
		SHARE_KEY_DOCTYPE,
		filters={
			"reference_doctype": SHARE_KEY_REFERENCE_DOCTYPE,
			"reference_docname": file_name,
		},
		fields=["name", "key", "expires_on"],
		order_by="creation desc",
	)

	for key in keys:
		if not is_expired(key.expires_on):
			return key

	return None


def get_file_share_info(file_name: str) -> dict:
	active_key = get_active_share_key(file_name)
	if not active_key:
		return {"key": None, "expires_on": None, "share_url": None}

	return {
		"key": active_key.key,
		"expires_on": active_key.expires_on,
		"share_url": get_share_link(file_name, active_key.key),
	}


def validate_file_share_key(file_name: str, token: str) -> bool:
	if not token:
		return False

	expires_on = frappe.db.get_value(
		SHARE_KEY_DOCTYPE,
		{
			"reference_doctype": SHARE_KEY_REFERENCE_DOCTYPE,
			"reference_docname": file_name,
			"key": token,
		},
		"expires_on",
	)

	if expires_on is None:
		return False

	if is_expired(expires_on):
		raise frappe.LinkExpired

	return True


def generate_file_share_key(file_name: str) -> dict:
	active_key = get_active_share_key(file_name)
	if active_key:
		return get_file_share_info(file_name)

	_create_share_key(file_name, get_share_key_expiry())
	return get_file_share_info(file_name)


def reset_file_share_key(file_name: str) -> dict:
	active_key = get_active_share_key(file_name)
	if not active_key:
		frappe.throw(_("No active share key found for this file"))

	frappe.db.set_value(
		SHARE_KEY_DOCTYPE,
		active_key.name,
		"expires_on",
		get_share_key_expiry(),
		update_modified=False,
	)

	return get_file_share_info(file_name)


def regenerate_file_share_key(file_name: str) -> dict:
	_delete_all_share_keys(file_name)
	_create_share_key(file_name, get_share_key_expiry())
	return get_file_share_info(file_name)


def revoke_file_share_key(file_name: str) -> dict:
	_delete_all_share_keys(file_name)
	return get_file_share_info(file_name)


def _create_share_key(file_name: str, expires_on):
	doc = frappe.new_doc(SHARE_KEY_DOCTYPE)
	doc.reference_doctype = SHARE_KEY_REFERENCE_DOCTYPE
	doc.reference_docname = file_name
	doc.expires_on = expires_on
	doc.insert(ignore_permissions=True)


def _delete_all_share_keys(file_name: str):
	frappe.db.delete(
		SHARE_KEY_DOCTYPE,
		{
			"reference_doctype": SHARE_KEY_REFERENCE_DOCTYPE,
			"reference_docname": file_name,
		},
	)
