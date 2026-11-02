// Copyright (c) 2026, Nest Software Development and contributors
// For license information, please see license.txt

frappe.query_reports["Open Check-ins"] = {
	filters: [
		{
			fieldname: "employee",
			label: __("Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "department",
			label: __("Department"),
			fieldtype: "Link",
			options: "Department",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const color = { [__("Due")]: "red", [__("Checked In")]: "green" }[data.status] || "orange";
			value = `<span class="indicator-pill ${color}">${value}</span>`;
		}
		return value;
	},
	onload(report) {
		report.page.add_inner_button(__("Run Watchdog Now"), () =>
			frappe.call({
				method: "kayan_attendance.api.run_watchdog_now",
				freeze: true,
				callback: () => report.refresh(),
			})
		);
	},
};
