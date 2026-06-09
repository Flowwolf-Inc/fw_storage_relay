// Copyright (c) 2026, Flowwolf Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("File", {
	refresh(frm) {
		if (!should_show_offload_button(frm)) {
			return;
		}

		const label =
			frm.doc.sync_status === "Failed"
				? __("Retry S3 Upload")
				: __("Upload to S3");

		frm.add_custom_button(label, () => offload_to_s3(frm), __("Actions"));
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
