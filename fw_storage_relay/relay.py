# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import mimetypes
import os
import traceback
from typing import TYPE_CHECKING

import frappe
from botocore.exceptions import ClientError
from frappe import _
from frappe.utils import get_url, now
from frappe.utils.file_manager import delete_file, save_file_on_filesystem

from fw_storage_relay.config import (
	STORAGE_BACKEND_S3,
	build_storage_key,
	can_offload_file,
	get_presigned_url_expiry,
	get_s3_config,
	should_make_files_public,
)
from fw_storage_relay.storage import get_backend

if TYPE_CHECKING:
	from frappe.core.doctype.file.file import File


def write_file(doc_or_fname, content=None, content_type=None, is_private=0):
	from frappe.core.doctype.file.file import File

	if isinstance(doc_or_fname, File):
		return _write_file_for_doc(doc_or_fname)

	return _write_file_for_file_manager(doc_or_fname, content, content_type=content_type, is_private=is_private)


def _write_file_for_file_manager(fname, content, content_type=None, is_private=0):
	return save_file_on_filesystem(fname, content, content_type=content_type, is_private=is_private)


def _write_file_for_doc(file_doc: File):
	if not can_offload_file(file_doc):
		return file_doc.save_file_on_filesystem()

	try:
		return _upload_to_s3(file_doc, file_doc._content, persist=False)
	except Exception as exc:
		_log_sync_error(file_doc, exc, persist=False)
		return file_doc.save_file_on_filesystem()


def after_insert_offload(doc: File, method=None):
	if doc.get("storage_backend") == STORAGE_BACKEND_S3:
		_refresh_s3_file_url(doc)
		return

	if _copy_s3_metadata_from_duplicate(doc, persist=True):
		_refresh_s3_file_url(doc)
		return

	if not can_offload_file(doc):
		return

	try:
		offload_file(doc, persist=True)
	except Exception as exc:
		_log_sync_error(doc, exc, persist=True)


def offload_file(file_doc: File, *, persist: bool = True) -> bool:
	if not can_offload_file(file_doc):
		return False

	if not file_doc.exists_on_disk():
		raise FileNotFoundError(f"Local file not found for {file_doc.name}")

	content = file_doc.get_content()
	if isinstance(content, str):
		content = content.encode()

	_upload_to_s3(file_doc, content, persist=persist)
	return True


def delete_file_data_content(doc: File, only_thumbnail=False):
	if only_thumbnail or doc.get("storage_backend") != STORAGE_BACKEND_S3:
		doc.delete_file_from_filesystem(only_thumbnail=only_thumbnail)
		return

	key = doc.get("cloud_storage_key")
	if not key:
		return

	try:
		get_backend().delete(key)
	except ClientError:
		frappe.log_error(
			title="FW Storage Relay S3 Delete Failed",
			message=f"File: {_file_log_identifier(doc)}\nKey: {key}\n\n{traceback.format_exc()}",
		)


def _upload_to_s3(file_doc: File, content: bytes, *, persist: bool):
	backend = get_backend()
	if result := _sync_from_duplicate(file_doc, persist=persist, delete_local=True):
		return result

	storage_key = build_storage_key(file_doc)
	content_type = mimetypes.guess_type(file_doc.file_name)[0]
	public = should_make_files_public()

	backend.upload(storage_key, content, content_type=content_type, public=public)

	file_url = _get_offloaded_file_url(file_doc, storage_key, backend)
	_delete_local_file(file_doc)

	_set_sync_success(file_doc, storage_key, file_url, persist=persist)
	return {"file_name": file_doc.file_name, "file_url": file_url}


def _get_synced_s3_duplicate(file_doc: File) -> dict | None:
	if not file_doc.content_hash:
		return None

	filters = {
		"content_hash": file_doc.content_hash,
		"is_private": file_doc.is_private,
		"storage_backend": STORAGE_BACKEND_S3,
		"sync_status": "Synced",
	}
	if file_doc.name:
		filters["name"] = ("!=", file_doc.name)

	return frappe.db.get_value(
		"File",
		filters,
		["name", "cloud_storage_key", "synced_on"],
		as_dict=True,
	)


def _sync_from_duplicate(file_doc: File, *, persist: bool, delete_local: bool = False) -> dict | None:
	duplicate = _get_synced_s3_duplicate(file_doc)
	if not duplicate or not duplicate.cloud_storage_key:
		return None

	backend = get_backend()
	file_url = _get_offloaded_file_url(file_doc, duplicate.cloud_storage_key, backend)
	if delete_local:
		_delete_local_file(file_doc)

	_set_sync_success(
		file_doc,
		duplicate.cloud_storage_key,
		file_url,
		persist=persist,
		synced_on=duplicate.synced_on,
	)
	return {"file_name": file_doc.file_name, "file_url": file_url}


def _copy_s3_metadata_from_duplicate(file_doc: File, *, persist: bool) -> bool:
	return _sync_from_duplicate(file_doc, persist=persist) is not None


def get_serve_file_url(file_name: str) -> str:
	return get_url(f"/api/method/fw_storage_relay.api.serve_file.serve_file?fid={file_name}")


def _get_offloaded_file_url(file_doc: File, storage_key: str, backend) -> str:
	if should_make_files_public():
		return backend.get_public_url(storage_key)

	if not file_doc.name:
		return None

	return get_serve_file_url(file_doc.name)


def _refresh_s3_file_url(file_doc: File):
	if should_make_files_public():
		return

	if file_doc.get("storage_backend") != STORAGE_BACKEND_S3 or not file_doc.name:
		return

	expected_fid = f"fid={file_doc.name}"
	if file_doc.file_url and expected_fid in file_doc.file_url:
		return

	file_url = get_serve_file_url(file_doc.name)
	frappe.db.set_value("File", file_doc.name, "file_url", file_url, update_modified=False)
	file_doc.file_url = file_url


def _set_sync_success(file_doc: File, storage_key: str, file_url: str | None, *, persist: bool, synced_on=None):
	values = {
		"storage_backend": STORAGE_BACKEND_S3,
		"cloud_storage_key": storage_key,
		"sync_status": "Synced",
		"synced_on": synced_on or now(),
		"sync_error": None,
	}
	if file_url:
		values["file_url"] = file_url

	if persist:
		frappe.db.set_value("File", file_doc.name, values, update_modified=False)
		file_doc.update(values)
	else:
		file_doc.update(values)


def _file_log_identifier(file_doc: File) -> str:
	if file_doc.name:
		return file_doc.name

	parts = [file_doc.file_name or "(unnamed)"]
	if file_doc.content_hash:
		parts.append(file_doc.content_hash[:12])

	return " / ".join(parts)


def _log_sync_error(file_doc: File, exc: Exception, *, persist: bool):
	error_message = str(exc)[:140]
	frappe.log_error(
		title="FW Storage Relay S3 Upload Failed",
		message=f"File: {_file_log_identifier(file_doc)}\n\n{traceback.format_exc()}",
	)

	values = {
		"storage_backend": "Local",
		"sync_status": "Failed",
		"sync_error": error_message,
	}

	if persist and file_doc.name:
		frappe.db.set_value("File", file_doc.name, values, update_modified=False)

	file_doc.update(values)


def _delete_local_file(file_doc: File):
	if not file_doc.file_url or file_doc.file_url.startswith(("http://", "https://")):
		return

	try:
		delete_file(file_doc.file_url)
	except OSError:
		local_path = file_doc.get_full_path()
		if os.path.exists(local_path):
			os.remove(local_path)


def generate_presigned_url(storage_key: str) -> str:
	return get_backend().get_presigned_url(storage_key, get_presigned_url_expiry())


def validate_relay_ready() -> bool:
	return bool(get_s3_config()) and frappe.db.get_single_value("FW S3 Relay Settings", "enabled")


def manual_offload_file(file_doc: File) -> dict:
	if not validate_relay_ready():
		frappe.throw(_("FW Storage Relay is disabled or S3 is not configured"))

	if not can_offload_file(file_doc):
		frappe.throw(_("This file cannot be uploaded to S3"))

	try:
		offload_file(file_doc, persist=True)
	except Exception as exc:
		_log_sync_error(file_doc, exc, persist=True)
		frappe.throw(_("S3 upload failed: {0}").format(str(exc)))

	return {
		"storage_backend": file_doc.storage_backend,
		"sync_status": file_doc.sync_status,
		"cloud_storage_key": file_doc.cloud_storage_key,
		"file_url": file_doc.file_url,
	}
