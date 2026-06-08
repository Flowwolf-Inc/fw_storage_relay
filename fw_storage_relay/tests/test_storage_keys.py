# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import re
import uuid
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from fw_storage_relay.config import build_storage_key, get_s3_object_name


class TestStorageKeys(FrappeTestCase):
	def test_get_s3_object_name_uses_uuid_and_extension(self):
		file_doc = type("File", (), {"file_name": "ILG.png"})()
		with patch("fw_storage_relay.config.uuid.uuid4", return_value=uuid.UUID("8f3a2b1c-4e5d-6789-abcd-ef0123456789")):
			object_name = get_s3_object_name(file_doc)

		self.assertEqual(object_name, "8f3a2b1c-4e5d-6789-abcd-ef0123456789.png")

	def test_get_s3_object_name_preserves_original_file_name(self):
		file_doc = type("File", (), {"file_name": "ILG.png"})()
		object_name = get_s3_object_name(file_doc)
		self.assertNotIn("ILG", object_name)
		self.assertTrue(object_name.endswith(".png"))

	def test_build_storage_key_uses_uuid_not_original_name(self):
		file_doc = type("File", (), {"file_name": "ILG.png", "is_private": 1})()
		with patch("fw_storage_relay.config.frappe.local") as local_mock:
			local_mock.site = "fuze"
			with patch("fw_storage_relay.config.get_s3_folder_prefix", return_value=""):
				with patch(
					"fw_storage_relay.config.uuid.uuid4",
					return_value=uuid.UUID("8f3a2b1c-4e5d-6789-abcd-ef0123456789"),
				):
					storage_key = build_storage_key(file_doc)

		self.assertEqual(storage_key, "fuze/private/8f3a2b1c-4e5d-6789-abcd-ef0123456789.png")
		self.assertNotIn("ILG", storage_key)

	def test_build_storage_key_uuid_format(self):
		file_doc = type("File", (), {"file_name": "report.PDF", "is_private": 0})()
		with patch("fw_storage_relay.config.frappe.local") as local_mock:
			local_mock.site = "fuze"
			with patch("fw_storage_relay.config.get_s3_folder_prefix", return_value=""):
				storage_key = build_storage_key(file_doc)

		object_name = storage_key.split("/")[-1]
		self.assertRegex(object_name, re.compile(r"^[0-9a-f-]{36}\.pdf$"))
