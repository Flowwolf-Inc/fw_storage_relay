// Copyright (c) 2026, Flowwolf Inc. and contributors
// For license information, please see license.txt

frappe.ui.form.on("FW S3 Relay Settings", {
	refresh(frm) {
		frm.set_intro(
			__(
				"AWS credentials are configured in site_config.json by DevOps and are not shown here."
			)
		);
	},
});
