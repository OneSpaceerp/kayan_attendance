frappe.listview_settings["Attendance Watchdog Log"] = {
	get_indicator(doc) {
		return doc.status === "Success"
			? [__("Success"), "green", "status,=,Success"]
			: [__("Failed"), "red", "status,=,Failed"];
	},
};
