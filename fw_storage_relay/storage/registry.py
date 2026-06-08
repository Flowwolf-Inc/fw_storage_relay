# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

from fw_storage_relay.config import STORAGE_BACKEND_S3
from fw_storage_relay.storage.s3 import S3Backend


def get_backend(name: str = STORAGE_BACKEND_S3):
	if name == STORAGE_BACKEND_S3:
		return S3Backend()

	raise NotImplementedError(f"Storage backend '{name}' is not implemented yet.")
