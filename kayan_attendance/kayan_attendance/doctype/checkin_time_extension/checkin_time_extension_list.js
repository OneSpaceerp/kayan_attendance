frappe.listview_settings["Checkin Time Extension"] = {
	add_fields: ["status"],
	has_indicator_for_draft: 1,
	get_indicator(doc) {
		const colors = { Open: "orange", Approved: "green", Rejected: "red", Cancelled: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
