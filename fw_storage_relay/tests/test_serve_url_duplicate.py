# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.overrides.file import CustomFile
from fw_storage_relay.patches.v1_0.link_serve_url_duplicates import execute as link_serve_url_duplicates
from fw_storage_relay.relay import (
	after_insert_offload,
	get_relay_source_file,
	get_serve_file_url,
	parse_serve_file_fid,
)


class TestServeUrlDuplicate(FrappeTestCase):
	def test_parse_serve_file_fid_ignores_host(self):
		self.assertEqual(
			parse_serve_file_fid(
				"https://lstgroup.apps.sandbox.flowwolf.link/api/method/"
				"fw_storage_relay.api.serve_file.serve_file?fid=530401ed1b"
			),
			"530401ed1b",
		)
		self.assertEqual(
			parse_serve_file_fid(
				"https://sandbox-lstgroup.flowwolf.cloud/api/method/"
				"fw_storage_relay.api.serve_file.serve_file?fid=530401ed1b&token=abc"
			),
			"530401ed1b",
		)
		self.assertIsNone(parse_serve_file_fid("/private/files/rate.pdf"))
		self.assertIsNone(parse_serve_file_fid(None))

	def test_insert_copies_synced_private_source(self):
		self._stub_s3_backend()
		source = self._insert_file(
			{
				"file_name": "rate_confirmation_without_page_2.pdf",
				"content": "source-content",
				"is_private": 1,
				"storage_backend": STORAGE_BACKEND_S3,
				"cloud_storage_key": "sandbox/private/00539c19-bd8a-4950-bd41-512af2cd4e55.pdf",
				"sync_status": "Synced",
				"content_hash": "c97414478dc90f3bcb9af7f41806e681",
			}
		)

		copy = self._insert_file(
			{
				"file_name": "rate_confirmation_without_page_2.pdf",
				"file_url": get_serve_file_url(source.name),
				"is_private": 0,
			}
		)
		copy.reload()

		self.assertEqual(int(copy.is_private or 0), 1)
		self.assertEqual(copy.storage_backend, STORAGE_BACKEND_S3)
		self.assertEqual(copy.sync_status, "Synced")
		self.assertEqual(copy.cloud_storage_key, source.cloud_storage_key)
		self.assertEqual(copy.content_hash, source.content_hash)
		self.assertIn(f"fid={copy.name}", copy.file_url)
		self.assertNotIn(f"fid={source.name}", copy.file_url)

	def test_insert_leaves_unsynced_source_pending_and_private(self):
		with patch("fw_storage_relay.relay.can_offload_file", return_value=False):
			source = self._insert_file(
				{
					"file_name": "unsynced.pdf",
					"content": "unsynced-content",
					"is_private": 1,
					"storage_backend": "Local",
					"sync_status": "Pending",
				}
			)
		serve_url = (
			"https://old-domain.example.com/api/method/"
			f"fw_storage_relay.api.serve_file.serve_file?fid={source.name}"
		)

		copy = self._insert_file(
			{
				"file_name": "unsynced.pdf",
				"file_url": serve_url,
				"is_private": 0,
			}
		)
		copy.reload()

		self.assertEqual(int(copy.is_private or 0), 1)
		self.assertEqual(copy.storage_backend, "Local")
		self.assertEqual(copy.sync_status, "Pending")
		self.assertFalse(copy.cloud_storage_key)
		self.assertIn(f"fid={source.name}", copy.file_url)

	def test_set_is_private_inherits_from_source(self):
		source = type(
			"Source",
			(),
			{"is_private": 1, "content_hash": "abc123"},
		)()
		file_doc = CustomFile(
			{
				"doctype": "File",
				"file_url": "https://example.com/api/method/fw_storage_relay.api.serve_file.serve_file?fid=src1",
				"is_private": 0,
			}
		)

		with patch("fw_storage_relay.overrides.file.get_relay_source_file", return_value=source):
			file_doc.set_is_private()

		self.assertEqual(file_doc.is_private, 1)
		self.assertEqual(file_doc.content_hash, "abc123")

	def test_after_insert_skips_unsynced_source(self):
		file_doc = type(
			"File",
			(),
			{
				"name": "copy1",
				"file_url": "https://example.com/api/method/fw_storage_relay.api.serve_file.serve_file?fid=src1",
				"storage_backend": "Local",
				"sync_status": "Pending",
				"get": lambda self, key, default=None: getattr(self, key, default),
			},
		)()

		with patch(
			"fw_storage_relay.relay.get_relay_source_file",
			return_value={
				"name": "src1",
				"is_private": 1,
				"storage_backend": "Local",
				"sync_status": "Pending",
				"cloud_storage_key": None,
				"content_hash": None,
				"synced_on": None,
			},
		):
			with patch("fw_storage_relay.relay._copy_s3_metadata_from_duplicate", return_value=False):
				with patch("fw_storage_relay.relay.can_offload_file", return_value=False):
					after_insert_offload(file_doc)

		self.assertEqual(file_doc.storage_backend, "Local")
		self.assertEqual(file_doc.sync_status, "Pending")

	def test_patch_links_existing_serve_url_copy(self):
		self._stub_s3_backend()
		source = self._insert_file(
			{
				"file_name": "already-synced.pdf",
				"content": "already-synced",
				"is_private": 1,
				"storage_backend": STORAGE_BACKEND_S3,
				"cloud_storage_key": "sandbox/private/already-synced.pdf",
				"sync_status": "Synced",
				"content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			}
		)
		stuck = self._insert_stuck_copy(source)

		link_serve_url_duplicates()
		stuck.reload()

		self.assertEqual(int(stuck.is_private or 0), 1)
		self.assertEqual(stuck.storage_backend, STORAGE_BACKEND_S3)
		self.assertEqual(stuck.sync_status, "Synced")
		self.assertEqual(stuck.cloud_storage_key, source.cloud_storage_key)
		self.assertIn(f"fid={stuck.name}", stuck.file_url)

	def test_patch_marks_missing_source_failed(self):
		stuck = self._insert_file(
			{
				"file_name": "orphan.pdf",
				"content": "orphan",
				"is_private": 0,
			}
		)
		frappe.db.set_value(
			"File",
			stuck.name,
			{
				"storage_backend": "Local",
				"sync_status": "Pending",
				"file_url": (
					"https://example.com/api/method/"
					"fw_storage_relay.api.serve_file.serve_file?fid=does-not-exist"
				),
			},
			update_modified=False,
		)

		link_serve_url_duplicates()
		stuck.reload()

		self.assertEqual(stuck.sync_status, "Failed")
		self.assertIn("does-not-exist", stuck.sync_error or "")

	def test_get_relay_source_file_returns_existing_row(self):
		self._stub_s3_backend()
		source = self._insert_file(
			{
				"file_name": "lookup.pdf",
				"content": "lookup",
				"is_private": 1,
				"storage_backend": STORAGE_BACKEND_S3,
				"cloud_storage_key": "sandbox/private/lookup.pdf",
				"sync_status": "Synced",
			}
		)
		found = get_relay_source_file(get_serve_file_url(source.name))
		self.assertEqual(found.name, source.name)
		self.assertEqual(found.cloud_storage_key, source.cloud_storage_key)

	def _stub_s3_backend(self):
		backend = patch("fw_storage_relay.overrides.file.get_backend").start()
		backend.return_value.exists.return_value = True
		self.addCleanup(patch.stopall)

	def _insert_file(self, values: dict):
		doc = frappe.get_doc({"doctype": "File", **values}).insert(ignore_permissions=True)
		self.addCleanup(self._cleanup_file, doc.name)
		return doc

	def _insert_stuck_copy(self, source):
		copy = self._insert_file(
			{
				"file_name": source.file_name,
				"content": "stuck-local-placeholder",
				"is_private": 0,
			}
		)
		frappe.db.set_value(
			"File",
			copy.name,
			{
				"storage_backend": "Local",
				"sync_status": "Pending",
				"cloud_storage_key": None,
				"is_private": 0,
				"file_url": get_serve_file_url(source.name),
			},
			update_modified=False,
		)
		copy.reload()
		return copy

	def _cleanup_file(self, name: str):
		if frappe.db.exists("File", name):
			frappe.delete_doc("File", name, ignore_permissions=True, force=True)

