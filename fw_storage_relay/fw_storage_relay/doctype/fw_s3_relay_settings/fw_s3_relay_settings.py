# Copyright (c) 2026, Flowwolf Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils.background_jobs import enqueue


class FWS3RelaySettings(Document):
	pass


# ---------------------------------------------------------------------------
# Scheduler entry points
# ---------------------------------------------------------------------------


def run_scheduled_migration_daily():
	settings = frappe.get_single("FW S3 Relay Settings")
	if not settings.enabled or not settings.enable_scheduled_migration:
		return
	_enqueue_migration(settings)


# ---------------------------------------------------------------------------
# Shared enqueue helper (also called by the "Migrate Now" whitelist method)
# ---------------------------------------------------------------------------


def _enqueue_migration(settings=None):
	if settings is None:
		settings = frappe.get_single("FW S3 Relay Settings")

	older_than_days = int(settings.older_than_days or 0)
	max_files = int(settings.max_files_per_run or 0)

	enqueue(
		"fw_storage_relay.commands.migrate._run_migration",
		queue="long",
		timeout=1500,
		batch_size=50,
		limit=max_files,
		workers=1,
		force=False,
		older_than_days=older_than_days,
		log=frappe.logger("fw_storage_relay").info,
	)


@frappe.whitelist()
def enqueue_migration_now():
	"""Enqueue an immediate S3 migration run using the current scheduler settings."""
	settings = frappe.get_single("FW S3 Relay Settings")

	if not settings.enabled:
		frappe.throw(_("FW Storage Relay is disabled."))

	_enqueue_migration(settings)
	frappe.msgprint(_("Migration queued. It may take a few minutes."))
