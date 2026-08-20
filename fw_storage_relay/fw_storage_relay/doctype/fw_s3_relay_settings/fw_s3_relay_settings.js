// Copyright (c) 2026, Flowwolf Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("FW S3 Relay Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"AWS credentials are configured in site_config.json by DevOps and are not shown here."
			)
		);

		if (frm.doc.enabled) {
			frm.add_custom_button(__("Migrate Now"), function () {
				frappe.confirm(
					__("Enqueue an S3 migration run using the current scheduled migration settings?"),
					function () {
						frappe.call({
							method:
								"fw_storage_relay.fw_storage_relay.doctype.fw_s3_relay_settings.fw_s3_relay_settings.enqueue_migration_now",
							callback(r) {
								if (!r.exc) {
									frappe.show_alert({
										message: __("Migration job queued."),
										indicator: "green",
									});
								}
							},
						});
					}
				);
			});
		}
	},
});
