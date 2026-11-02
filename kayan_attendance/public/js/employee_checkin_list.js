// Marks the check-outs written by the Kayan Attendance watchdog in the Employee Checkin list.
// Loaded after the HRMS list settings, so it extends them instead of replacing them.
(() => {
	const settings = (frappe.listview_settings["Employee Checkin"] ||= {});
	const hrms_indicator = settings.get_indicator;

	settings.add_fields = [...(settings.add_fields || []), "kayan_auto_checkout"];
	settings.get_indicator = function (doc) {
		if (doc.kayan_auto_checkout) {
			return [__("Auto Check-out"), "orange", "kayan_auto_checkout,=,1"];
		}
		return hrms_indicator?.call(this, doc);
	};
})();
