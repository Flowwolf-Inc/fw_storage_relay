# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from fw_storage_relay.relay import manual_offload_file


class TestManualOffload(FrappeTestCase):
	def test_manual_offload_raises_when_relay_not_ready(self):
		file_doc = type("File", (), {"is_folder": 0, "is_remote_file": 0})()
		with patch("fw_storage_relay.relay.validate_relay_ready", return_value=False):
			with self.assertRaises(frappe.exceptions.ValidationError):
				manual_offload_file(file_doc)

	def test_manual_offload_raises_when_cannot_offload(self):
		file_doc = type("File", (), {"is_folder": 0, "is_remote_file": 0})()
		with patch("fw_storage_relay.relay.validate_relay_ready", return_value=True):
			with patch("fw_storage_relay.relay.can_offload_file", return_value=False):
				with self.assertRaises(frappe.exceptions.ValidationError):
					manual_offload_file(file_doc)
