// Copyright (c) 2026, Flowwolf Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("File", {
	refresh(frm) {
		if (should_show_offload_button(frm)) {
			const label =
				frm.doc.sync_status === "Failed"
					? __("Retry S3 Upload")
					: __("Upload to S3");

			frm.add_custom_button(label, () => offload_to_s3(frm), __("Actions"));
		}

		if (should_show_share_buttons(frm)) {
			setup_share_buttons(frm);
		}
	},
});

function should_show_offload_button(frm) {
	if (frm.is_new() || frm.doc.is_folder || frm.doc.is_remote_file) {
		return false;
	}

	if (frm.doc.storage_backend === "S3" && frm.doc.sync_status === "Synced") {
		return false;
	}

	return ["Pending", "Failed"].includes(frm.doc.sync_status) || frm.doc.storage_backend === "Local";
}

function should_show_share_buttons(frm) {
	if (frm.is_new() || frm.doc.is_folder || frm.doc.is_remote_file) {
		return false;
	}

	return frm.doc.storage_backend === "S3" && frm.doc.sync_status === "Synced";
}

function setup_share_buttons(frm) {
	frappe.call({
		method: "fw_storage_relay.api.file_share.get_file_share_info",
		args: { file_name: frm.doc.name },
		callback(r) {
			if (r.exc) {
				return;
			}

			const info = r.message || {};
			const has_active_key = !!(info.key && info.share_url);

			if (!has_active_key) {
				frm.add_custom_button(
					__("Generate Share Link"),
					() => generate_share_link(frm),
					__("Actions")
				);
				return;
			}

			frm.add_custom_button(
				__("Copy Share Link"),
				() => {
					frappe.utils.copy_to_clipboard(info.share_url);
					frappe.show_alert({
						message: __("Share link copied"),
						indicator: "green",
					});
				},
				__("Actions")
			);

			frm.add_custom_button(
				__("Reset Share Expiry"),
				() => reset_share_key(frm),
				__("Actions")
			);

			frm.add_custom_button(
				__("Regenerate Share Key"),
				() => {
					frappe.confirm(
						__(
							"This will invalidate the current link. Update Salesforce with the new URL."
						),
						() => regenerate_share_key(frm)
					);
				},
				__("Actions")
			);

			frm.add_custom_button(
				__("Revoke Share Key"),
				() => {
					frappe.confirm(
						__("This will revoke guest access via the share link."),
						() => revoke_share_key(frm)
					);
				},
				__("Actions")
			);
		},
	});
}

function generate_share_link(frm) {
	call_share_method(frm, "generate_file_share_key", __("Generating share link..."));
}

function reset_share_key(frm) {
	call_share_method(frm, "reset_file_share_key", __("Resetting share expiry..."));
}

function regenerate_share_key(frm) {
	call_share_method(frm, "regenerate_file_share_key", __("Regenerating share key..."));
}

function revoke_share_key(frm) {
	frappe.call({
		method: "fw_storage_relay.api.file_share.revoke_file_share_key",
		args: { file_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Revoking share key..."),
		callback(r) {
			if (!r.exc) {
				frappe.show_alert({
					message: __("Share key revoked"),
					indicator: "green",
				});
				frm.reload_doc();
			}
		},
	});
}

function call_share_method(frm, method, freeze_message) {
	frappe.call({
		method: `fw_storage_relay.api.file_share.${method}`,
		args: { file_name: frm.doc.name },
		freeze: true,
		freeze_message,
		callback(r) {
			if (!r.exc && r.message) {
				show_share_link_dialog(r.message);
				frm.reload_doc();
			}
		},
	});
}

function show_share_link_dialog(info) {
	const fields = [
		{
			fieldname: "share_url",
			fieldtype: "Small Text",
			label: __("Share Link"),
			read_only: 1,
			default: info.share_url,
		},
		{
			fieldname: "token",
			fieldtype: "Data",
			label: __("Token"),
			read_only: 1,
			default: info.key,
		},
		{
			fieldname: "expires_on",
			fieldtype: "Date",
			label: __("Expires On"),
			read_only: 1,
			default: info.expires_on,
		},
	];

	const dialog = new frappe.ui.Dialog({
		title: __("File Share Link"),
		fields,
		primary_action_label: __("Copy Link"),
		primary_action() {
			frappe.utils.copy_to_clipboard(info.share_url);
			frappe.show_alert({
				message: __("Share link copied"),
				indicator: "green",
			});
			dialog.hide();
		},
	});

	dialog.show();
}

function offload_to_s3(frm) {
	frappe.call({
		method: "fw_storage_relay.api.offload.offload_to_s3",
		args: { file_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Uploading to S3..."),
		callback(r) {
			if (!r.exc) {
				frappe.show_alert({
					message: __("File uploaded to S3"),
					indicator: "green",
				});
				frm.reload_doc();
			}
		},
	});
}
