import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, get_time, getdate

from kayan_attendance.attendance_watchdog import get_normal_checkout_time, get_settings


def after_insert(doc, method=None):
    """An employee who checks in again after being checked out automatically is still at work.

    The Frappe HR mobile app shows "Check In" once the watchdog has written the OUT log, so the
    employee taps it and this IN arrives here. When the settings allow, it raises a Checkin Time
    Extension for the rest of the session, so the next automatic check-out lands at its end.
    """
    if doc.flags.kayan_auto_checkout or doc.log_type != "IN":
        return

    settings = get_settings()
    if not (cint(settings.allow_extensions) and cint(settings.request_extension_on_recheckin)):
        return

    previous = frappe.get_all(
        "Employee Checkin",
        filters={"employee": doc.employee, "time": ("<", doc.time), "name": ("!=", doc.name)},
        fields=["name", "log_type", "time", "kayan_auto_checkout"],
        order_by="time desc",
        limit=1,
    )
    if not previous or not previous[0].kayan_auto_checkout:
        return
    if getdate(previous[0].time) != getdate(doc.time):
        return

    date = getdate(doc.time)
    if frappe.db.exists(
        "Checkin Time Extension",
        {"employee": doc.employee, "date": date, "docstatus": ("<", 2), "status": ("!=", "Rejected")},
    ):
        return

    hours = flt(settings.default_extension_hours) or 2
    until = add_to_date(get_datetime(doc.time), hours=hours)
    if flt(settings.max_extension_hours):
        normal = get_normal_checkout_time(doc.employee, date, settings)
        until = min(until, add_to_date(normal, hours=flt(settings.max_extension_hours)))
    if getdate(until) != date:
        until = get_datetime(f"{date} 23:59:00")
    if until <= get_datetime(doc.time):
        # past the longest extension allowed; the watchdog's late session rule closes this one
        return

    # never let the request get in the way of the check-in itself
    frappe.db.savepoint("kayan_extension_request")
    try:
        extension = frappe.get_doc(
            {
                "doctype": "Checkin Time Extension",
                "employee": doc.employee,
                "date": date,
                "extended_until": get_time(until).strftime("%H:%M:%S"),
                "source": "Re-check-in",
                "reason": _("Checked in again at {0} after the automatic check-out.").format(
                    get_datetime(doc.time).strftime("%H:%M")
                ),
            }
        )
        extension.flags.ignore_permissions = True
        extension.insert()

        if cint(settings.auto_approve_recheckin_extensions):
            extension.status = "Approved"
            extension.flags.ignore_permissions = True
            extension.submit()
    except Exception:
        frappe.db.rollback(save_point="kayan_extension_request")
        frappe.log_error(
            title=_("Kayan Attendance: extension request failed"),
            reference_doctype="Employee Checkin",
            reference_name=doc.name,
        )
