frappe.pages["storage-stats"].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Cloud Storage Stats"),
		single_column: true,
	});

	page.add_inner_button(__("Refresh"), function () {
		load_stats(page);
	});

	page.add_inner_button(__("View Failed Files"), function () {
		frappe.set_route("List", "File", { sync_status: "Failed" });
	});

	page.add_inner_button(__("View Pending Files"), function () {
		frappe.set_route("List", "File", { sync_status: "Pending" });
	});

	frappe.breadcrumbs.add("FW Storage Relay");

	$(frappe.render_template("storage_stats", {})).appendTo(
		page.body.addClass("no-border")
	);

	load_stats(page);
};

frappe.pages["storage-stats"].on_page_show = function (wrapper) {
	// refresh data every time the user navigates back to the page
	var page = wrapper.page;
	if (page) {
		load_stats(page);
	}
};

function load_stats(page) {
	page.set_indicator(__("Loading…"), "blue");

	frappe.call({
		method: "fw_storage_relay.api.stats.get_storage_stats",
		callback: function (r) {
			if (r.exc) {
				page.set_indicator(__("Error"), "red");
				return;
			}
			render_stats(r.message);
			page.clear_indicator();
		},
		error: function () {
			page.set_indicator(__("Error"), "red");
		},
	});
}

function render_stats(data) {
	// Sync status
	set_val("count-synced", data.synced);
	set_val("count-pending", data.pending);
	set_val("count-failed", data.failed);
	set_val("count-total", data.total);

	// Local folder counts
	var local = data.local || {};
	set_val("count-local-private", local.private);
	set_val("count-local-public", local.public);
	set_val("count-local-backup", local.backup);

	// Offload progress bar
	var total = data.total || 0;
	var synced = data.synced || 0;
	var pct = total > 0 ? Math.round((synced / total) * 100) : 0;

	var wrap = $("#offload-progress-wrap");
	if (total > 0) {
		wrap.show();
		$("#offload-progress-bar").css("width", pct + "%");
		$("#offload-pct-label").text(pct + "%");
	} else {
		wrap.hide();
	}

	// Last refreshed timestamp
	var ts = frappe.datetime.now_datetime();
	$("#last-refreshed").text(__("Last refreshed: {0}", [ts]));
}

function set_val(id, value) {
	var el = document.getElementById(id);
	if (el) {
		el.textContent = value !== undefined && value !== null ? value : "0";
	}
}
