# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_months, getdate

from fw_storage_relay.api.serve_file import serve_file
from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.share_key import (
	generate_file_share_key,
	get_file_share_info,
	get_share_link,
	regenerate_file_share_key,
	reset_file_share_key,
	revoke_file_share_key,
	validate_file_share_key,
)


class TestFileShareKey(FrappeTestCase):
	def setUp(self):
		self.file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "share-key-test.txt",
				"content": "share key test content",
				"is_private": 1,
				"storage_backend": STORAGE_BACKEND_S3,
				"cloud_storage_key": "fuze/private/share-key-test.txt",
				"sync_status": "Synced",
			}
		).insert(ignore_permissions=True)
		self.addCleanup(self._cleanup_file)

	def _cleanup_file(self):
		frappe.db.delete(
			"Document Share Key",
			{
				"reference_doctype": "File",
				"reference_docname": self.file_doc.name,
			},
		)
		if frappe.db.exists("File", self.file_doc.name):
			frappe.delete_doc("File", self.file_doc.name, ignore_permissions=True, force=True)

	def test_generate_returns_existing_active_key(self):
		first = generate_file_share_key(self.file_doc.name)
		second = generate_file_share_key(self.file_doc.name)

		self.assertEqual(first["key"], second["key"])
		self.assertIn(f"fid={self.file_doc.name}", first["share_url"])
		self.assertIn(f"token={first['key']}", first["share_url"])

	def test_reset_keeps_same_key_and_extends_expiry(self):
		info = generate_file_share_key(self.file_doc.name)
		original_key = info["key"]

		key_doc = frappe.get_doc("Document Share Key", {"key": original_key})
		key_doc.expires_on = add_months(getdate(), 1)
		key_doc.save(ignore_permissions=True)

		reset_info = reset_file_share_key(self.file_doc.name)

		self.assertEqual(reset_info["key"], original_key)
		self.assertGreater(getdate(reset_info["expires_on"]), getdate(add_months(getdate(), 1)))

	def test_regenerate_issues_new_key(self):
		first = generate_file_share_key(self.file_doc.name)
		second = regenerate_file_share_key(self.file_doc.name)

		self.assertNotEqual(first["key"], second["key"])

	def test_revoke_removes_active_key(self):
		generate_file_share_key(self.file_doc.name)
		info = revoke_file_share_key(self.file_doc.name)

		self.assertIsNone(info["key"])
		self.assertIsNone(info["share_url"])

	def test_validate_file_share_key_rejects_invalid_token(self):
		generate_file_share_key(self.file_doc.name)
		self.assertFalse(validate_file_share_key(self.file_doc.name, "invalid-token"))

	def test_validate_file_share_key_raises_for_expired_token(self):
		info = generate_file_share_key(self.file_doc.name)
		key_doc = frappe.get_doc("Document Share Key", {"key": info["key"]})
		key_doc.expires_on = "2020-01-01"
		key_doc.save(ignore_permissions=True)

		with self.assertRaises(frappe.LinkExpired):
			validate_file_share_key(self.file_doc.name, info["key"])

	@patch("fw_storage_relay.api.serve_file.generate_presigned_url", return_value="https://s3.example/file")
	def test_guest_with_valid_token_can_serve_file(self, _mock_presign):
		info = generate_file_share_key(self.file_doc.name)

		frappe.set_user("Guest")
		frappe.form_dict.fid = self.file_doc.name
		frappe.form_dict.token = info["key"]

		serve_file(self.file_doc.name, info["key"])

		self.assertEqual(frappe.local.response["type"], "redirect")
		self.assertEqual(frappe.local.response["location"], "https://s3.example/file")
		frappe.set_user("Administrator")

	@patch("fw_storage_relay.api.serve_file.generate_presigned_url", return_value="https://s3.example/file")
	def test_guest_without_token_on_private_file_is_denied(self, _mock_presign):
		frappe.set_user("Guest")

		with self.assertRaises(frappe.PermissionError):
			serve_file(self.file_doc.name, None)

		frappe.set_user("Administrator")

	@patch("fw_storage_relay.api.serve_file.generate_presigned_url", return_value="https://s3.example/file")
	def test_guest_with_expired_token_raises_link_expired(self, _mock_presign):
		info = generate_file_share_key(self.file_doc.name)
		key_doc = frappe.get_doc("Document Share Key", {"key": info["key"]})
		key_doc.expires_on = "2020-01-01"
		key_doc.save(ignore_permissions=True)

		frappe.set_user("Guest")

		with self.assertRaises(frappe.LinkExpired):
			serve_file(self.file_doc.name, info["key"])

		frappe.set_user("Administrator")

	@patch("fw_storage_relay.api.serve_file.generate_presigned_url", return_value="https://s3.example/file")
	def test_logged_in_user_ignores_token(self, _mock_presign):
		frappe.set_user("Administrator")

		serve_file(self.file_doc.name, "invalid-token")

		self.assertEqual(frappe.local.response["type"], "redirect")
		self.assertEqual(frappe.local.response["location"], "https://s3.example/file")

	def test_get_share_link_includes_fid_and_token(self):
		info = generate_file_share_key(self.file_doc.name)
		link = get_share_link(self.file_doc.name, info["key"])

		self.assertIn(f"fid={self.file_doc.name}", link)
		self.assertIn(f"token={info['key']}", link)

	def test_get_file_share_info_without_key(self):
		info = get_file_share_info(self.file_doc.name)
		self.assertIsNone(info["key"])
		self.assertIsNone(info["share_url"])
