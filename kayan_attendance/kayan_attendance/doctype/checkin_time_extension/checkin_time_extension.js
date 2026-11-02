// Copyright (c) 2026, Nest Software Development and contributors
// For license information, please see license.txt

frappe.ui.form.on("Checkin Time Extension", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.is_new() && frm.doc.status === "Open") {
			frm.add_custom_button(
				__("Approve"),
				() => frm.set_value("status", "Approved").then(() => frm.savesubmit()),
				__("Actions")
			);
			frm.add_custom_button(
				__("Reject"),
				() => frm.set_value("status", "Rejected").then(() => frm.savesubmit()),
				__("Actions")
			);
		}
	},
});
