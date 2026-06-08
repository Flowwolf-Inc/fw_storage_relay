# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import uuid
from typing import TYPE_CHECKING

import frappe
from frappe.utils.caching import site_cache

if TYPE_CHECKING:
	from frappe.core.doctype.file.file import File


SETTINGS_DOCTYPE = "FW S3 Relay Settings"
STORAGE_BACKEND_S3 = "S3"


@site_cache
def get_s3_config() -> dict | None:
	access_key = frappe.conf.get("fw_s3_access_key")
	secret_key = frappe.conf.get("fw_s3_secret_key")
	region = frappe.conf.get("fw_s3_region")
	bucket = frappe.conf.get("fw_s3_bucket")

	if not all([access_key, secret_key, region, bucket]):
		return None

	return {
		"access_key": access_key,
		"secret_key": secret_key,
		"region": region,
		"bucket": bucket,
	}


def is_relay_enabled() -> bool:
	if not frappe.db.table_exists("tabFW S3 Relay Settings"):
		return False

	return bool(frappe.db.get_single_value(SETTINGS_DOCTYPE, "enabled"))


@site_cache
def get_excluded_doctypes() -> frozenset[str]:
	if not frappe.db.table_exists("tabFW S3 Relay Excluded Doctype"):
		return frozenset()

	rows = frappe.get_all(
		"FW S3 Relay Excluded Doctype",
		filters={"parent": SETTINGS_DOCTYPE, "parenttype": SETTINGS_DOCTYPE},
		pluck="doctype_name",
	)
	return frozenset(rows)


def is_doctype_excluded(doctype: str | None) -> bool:
	if not doctype:
		return False

	return doctype in get_excluded_doctypes()


def get_s3_folder_prefix() -> str:
	prefix = frappe.db.get_single_value(SETTINGS_DOCTYPE, "s3_folder_prefix") or ""
	return prefix if prefix.endswith("/") else f"{prefix}/" if prefix else ""


def should_make_files_public() -> bool:
	return bool(frappe.db.get_single_value(SETTINGS_DOCTYPE, "make_files_public"))


def get_presigned_url_expiry() -> int:
	return int(frappe.db.get_single_value(SETTINGS_DOCTYPE, "presigned_url_expiry") or 3600)


def get_s3_object_name(file_doc: File) -> str:
	ext = os.path.splitext(file_doc.file_name or "")[1].lower()
	return f"{uuid.uuid4()}{ext}"


def build_storage_key(file_doc: File) -> str:
	visibility = "private" if file_doc.is_private else "public"
	object_name = get_s3_object_name(file_doc)
	return f"{get_s3_folder_prefix()}{frappe.local.site}/{visibility}/{object_name}"


def can_offload_file(file_doc: File) -> bool:
	if file_doc.is_folder or file_doc.is_remote_file:
		return False

	if file_doc.get("storage_backend") == STORAGE_BACKEND_S3 and file_doc.get("sync_status") == "Synced":
		return False

	if not is_relay_enabled() or not get_s3_config():
		return False

	return not is_doctype_excluded(file_doc.attached_to_doctype)
