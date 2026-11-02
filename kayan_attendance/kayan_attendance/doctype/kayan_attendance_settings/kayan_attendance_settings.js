// Copyright (c) 2026, Nest Software Development and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kayan Attendance Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Run Watchdog Now"), () => {
			frappe.call({
				method: "kayan_attendance.api.run_watchdog_now",
				freeze: true,
				freeze_message: __("Checking open check-ins..."),
				callback: (r) => {
					const s = r.message || {};
					frappe.show_alert({
						message: __("Closed {0}, failed {1}, still open {2}", [
							s.closed || 0,
							s.failed || 0,
							s.waiting || 0,
						]),
						indicator: s.failed ? "orange" : "green",
					});
					frm.reload_doc();
				},
			});
		});
		frm.add_custom_button(__("Open Check-ins"), () =>
			frappe.set_route("query-report", "Open Check-ins")
		);
	},
});
