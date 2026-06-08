# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from fw_storage_relay.relay import _get_offloaded_file_url, get_serve_file_url


class TestFileUrl(FrappeTestCase):
	def test_get_serve_file_url_includes_fid(self):
		url = get_serve_file_url("e3cc60252d")
		self.assertIn("fid=e3cc60252d", url)

	def test_get_offloaded_file_url_without_name_returns_none(self):
		file_doc = type("File", (), {"name": None})()
		with patch("fw_storage_relay.relay.should_make_files_public", return_value=False):
			self.assertIsNone(_get_offloaded_file_url(file_doc, "fuze/public/test.png", None))

	def test_get_offloaded_file_url_with_name(self):
		file_doc = type("File", (), {"name": "abc123"})()
		with patch("fw_storage_relay.relay.should_make_files_public", return_value=False):
			url = _get_offloaded_file_url(file_doc, "fuze/public/test.png", None)
		self.assertIn("fid=abc123", url)
