# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.core.doctype.file.file import File

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.share_key import (
	generate_file_share_key as _generate_file_share_key,
	get_file_share_info as _get_file_share_info,
	regenerate_file_share_key as _regenerate_file_share_key,
	reset_file_share_key as _reset_file_share_key,
	revoke_file_share_key as _revoke_file_share_key,
)
from fw_storage_relay.storage import get_backend


class CustomFile(File):
	def get_content(self) -> bytes:
		if self.get("storage_backend") == STORAGE_BACKEND_S3 and self.get("cloud_storage_key"):
			return get_backend().download(self.cloud_storage_key)

		return super().get_content()

	def exists_on_disk(self):
		if self.get("storage_backend") == STORAGE_BACKEND_S3 and self.get("sync_status") == "Synced":
			key = self.get("cloud_storage_key")
			if key:
				return get_backend().exists(key)

		return super().exists_on_disk()

	def validate_file_on_disk(self):
		if self.get("storage_backend") == STORAGE_BACKEND_S3:
			return True

		return super().validate_file_on_disk()

	@frappe.whitelist()
	def get_file_share_info(self):
		if not self.has_permission("read"):
			frappe.throw(_("You do not have permission to access this file"), frappe.PermissionError)
		return _get_file_share_info(self.name)

	@frappe.whitelist()
	def generate_file_share_key(self):
		self._require_file_write_permission()
		return _generate_file_share_key(self.name)

	@frappe.whitelist()
	def reset_file_share_key(self):
		self._require_file_write_permission()
		return _reset_file_share_key(self.name)

	@frappe.whitelist()
	def regenerate_file_share_key(self):
		self._require_file_write_permission()
		return _regenerate_file_share_key(self.name)

	@frappe.whitelist()
	def revoke_file_share_key(self):
		self._require_file_write_permission()
		return _revoke_file_share_key(self.name)

	def _require_file_write_permission(self):
		if not self.has_permission("write"):
			frappe.throw(_("You do not have permission to modify this file"), frappe.PermissionError)
