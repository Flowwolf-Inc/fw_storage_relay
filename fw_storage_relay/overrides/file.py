# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from frappe.core.doctype.file.file import File

from fw_storage_relay.config import STORAGE_BACKEND_S3
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
