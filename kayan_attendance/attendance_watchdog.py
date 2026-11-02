"""Attendance watchdog: closes check-ins that were never checked out.

An open check-in is an IN log whose next log for the same employee is not an OUT (either nothing
follows yet, or the employee checked in again the next day). The Frappe HR mobile app decides its
button from the latest log only, so an open IN leaves the app offering "Check Out" for ever; the OUT
written here puts the app back on "Check In" and gives HRMS auto attendance a complete pair.

Each open check-in gets its own check-out time:

    Fixed Time    the date of the check-in at the time set in Kayan Attendance Settings (17:00)
    Shift End     the shift end HRMS stored on the check-in, when the settings choose it
    Extension     an approved Checkin Time Extension for that employee and date, when later
    Late Session  check-in after all of the above: the check-in time plus the late session hours

and is closed once that time (plus the grace minutes) has passed.
"""

import datetime

import frappe
from frappe import _
from frappe.utils import (
    add_days,
    add_to_date,
    cint,
    flt,
    format_datetime,
    get_datetime,
    get_time,
    getdate,
    now_datetime,
)

AUTO_CHECKOUT_DEVICE = "Kayan Auto Checkout"

RULE_FIXED_TIME = "Fixed Time"
RULE_SHIFT_END = "Shift End"
RULE_EXTENSION = "Extension"
RULE_LATE_SESSION = "Late Session"


def get_settings():
    return frappe.get_cached_doc("Kayan Attendance Settings")


def run():
    """Scheduler entry point (every 10 minutes)."""
    settings = get_settings()
    if not cint(settings.enable_watchdog):
        return

    now = now_datetime()
    summary = {"closed": 0, "failed": 0, "waiting": 0}

    for session in get_open_sessions(settings, now):
        if session.checkout_time is None:
            continue
        if now < add_to_date(session.checkout_time, minutes=cint(settings.grace_minutes)):
            summary["waiting"] += 1
            continue

        if close_session(session, settings):
            summary["closed"] += 1
        else:
            summary["failed"] += 1

    frappe.db.set_single_value(
        "Kayan Attendance Settings",
        {
            "last_run_on": now,
            "last_run_summary": _("Closed {0}, failed {1}, still open {2}").format(
                summary["closed"], summary["failed"], summary["waiting"]
            ),
        },
        # keeps the settings form free of "document has been modified" every 10 minutes
        update_modified=False,
    )
    frappe.db.commit()
    return summary


def get_open_sessions(settings, now=None, employee=None):
    """Open check-ins of the last `lookback_days` days, each with its planned check-out time."""
    now = now or now_datetime()
    window_start = get_datetime(add_days(getdate(now), -max(cint(settings.lookback_days), 1)))

    filters = {"time": (">=", window_start)}
    if employee:
        filters["employee"] = employee

    logs = frappe.get_all(
        "Employee Checkin",
        filters=filters,
        fields=[
            "name",
            "employee",
            "employee_name",
            "log_type",
            "time",
            "shift_end",
            "latitude",
            "longitude",
        ],
        order_by="employee asc, time asc",
    )

    skipped = set(
        frappe.get_all(
            "Employee",
            filters={"kayan_skip_auto_checkout": 1},
            pluck="name",
        )
    )

    sessions = []
    for index, log in enumerate(logs):
        if log.log_type != "IN" or log.employee in skipped:
            continue

        following = logs[index + 1] if index + 1 < len(logs) else None
        if following and following.employee != log.employee:
            following = None
        if following and following.log_type != "IN":
            # closed by an OUT, or followed by a log without a type we cannot reason about
            continue

        extension = get_approved_extension(log.employee, getdate(log.time))
        resolved = resolve_checkout_time(
            log.time,
            fixed_time=settings.auto_checkout_time or "17:00:00",
            shift_end=log.shift_end if settings.checkout_time_based_on == RULE_SHIFT_END else None,
            extended_until=extension.extended_until if extension else None,
            late_session_hours=flt(settings.late_session_hours),
            next_check_in=following.time if following else None,
        )

        log.checkout_time, log.rule = resolved if resolved else (None, None)
        log.extension = extension.name if extension and log.rule == RULE_EXTENSION else None
        sessions.append(log)

    return sessions


def resolve_checkout_time(
    check_in,
    fixed_time,
    shift_end=None,
    extended_until=None,
    late_session_hours=0,
    next_check_in=None,
):
    """Return (checkout_time, rule) for an open check-in, or None when no valid time exists.

    Pure function so it can be tested without a site.
    """
    check_in = get_datetime(check_in)
    day = check_in.date()

    if shift_end:
        checkout_time, rule = get_datetime(shift_end), RULE_SHIFT_END
    else:
        checkout_time, rule = datetime.datetime.combine(day, get_time(fixed_time)), RULE_FIXED_TIME

    if extended_until:
        extended = datetime.datetime.combine(day, get_time(extended_until))
        if extended > checkout_time:
            checkout_time, rule = extended, RULE_EXTENSION

    if checkout_time <= check_in:
        # checked in after the end of the working day, e.g. back again after an automatic check-out
        end_of_day = datetime.datetime.combine(day, datetime.time(23, 59, 59))
        checkout_time = min(check_in + datetime.timedelta(hours=late_session_hours), end_of_day)
        rule = RULE_LATE_SESSION

    if next_check_in:
        # never write an OUT after the employee's next IN
        checkout_time = min(checkout_time, get_datetime(next_check_in) - datetime.timedelta(seconds=1))

    if checkout_time <= check_in:
        return None

    return checkout_time, rule


def get_approved_extension(employee, date):
    return frappe.db.get_value(
        "Checkin Time Extension",
        {"employee": employee, "date": date, "status": "Approved", "docstatus": 1},
        ["name", "extended_until"],
        as_dict=True,
        order_by="extended_until desc",
    )


def close_session(session, settings):
    """Write the OUT log for one open check-in. Returns True when it was written."""
    savepoint = "kayan_auto_checkout"
    frappe.db.savepoint(savepoint)
    try:
        checkout = frappe.new_doc("Employee Checkin")
        checkout.update(
            {
                "employee": session.employee,
                "log_type": "OUT",
                "time": session.checkout_time,
                "device_id": AUTO_CHECKOUT_DEVICE,
                # the check-in's own coordinates, so HRMS geofencing accepts the log
                "latitude": session.latitude,
                "longitude": session.longitude,
                "kayan_auto_checkout": 1,
                "kayan_checkout_rule": session.rule,
                "kayan_source_checkin": session.name,
                "kayan_extension": session.extension,
            }
        )
        checkout.flags.kayan_auto_checkout = True
        checkout.insert(ignore_permissions=True)
    except Exception:
        frappe.db.rollback(save_point=savepoint)
        record_log(session, status="Failed", error=frappe.get_traceback(with_context=True))
        frappe.db.commit()
        return False

    record_log(session, status="Success", checkout=checkout.name)
    if cint(settings.notify_employee):
        notify_employee(session)
    frappe.db.commit()
    return True


def record_log(session, status, checkout=None, error=None):
    # one log per check-in: a check-in that keeps failing updates its row instead of adding one per run
    name = frappe.db.get_value("Attendance Watchdog Log", {"check_in": session.name})
    log = (
        frappe.get_doc("Attendance Watchdog Log", name) if name else frappe.new_doc("Attendance Watchdog Log")
    )
    log.update(
        {
            "employee": session.employee,
            "employee_name": session.employee_name,
            "attendance_date": getdate(session.time),
            "check_in": session.name,
            "check_in_time": session.time,
            "checkout_time": session.checkout_time,
            "rule": session.rule,
            "checkin_time_extension": session.extension,
            "status": status,
            "auto_checkout": checkout,
            "attempts": cint(log.attempts) + 1,
            "error": error,
        }
    )
    log.flags.ignore_permissions = True
    log.save()


def notify_employee(session):
    user = frappe.db.get_value("Employee", session.employee, "user_id")
    if not user:
        return

    message = _("You were checked out automatically at {0} because no check-out was recorded.").format(
        format_datetime(session.checkout_time, "HH:mm")
    )
    create_app_notification(user, message, "Employee Checkin", session.name)


def create_app_notification(to_user, message, reference_doctype, reference_name):
    """A PWA Notification shows in the Frappe HR mobile app's notifications and is pushed when enabled."""
    try:
        frappe.get_doc(
            {
                "doctype": "PWA Notification",
                "from_user": frappe.session.user if frappe.session.user != "Guest" else "Administrator",
                "to_user": to_user,
                "message": message,
                "reference_document_type": reference_doctype,
                "reference_document_name": reference_name,
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title=_("Kayan Attendance: notification failed"))


def get_normal_checkout_time(employee, date, settings=None):
    """The check-out time an employee has on `date` before any extension."""
    settings = settings or get_settings()
    date = getdate(date)
    fixed = datetime.datetime.combine(date, get_time(settings.auto_checkout_time or "17:00:00"))

    if settings.checkout_time_based_on == RULE_SHIFT_END:
        from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift

        shift = get_employee_shift(employee, datetime.datetime.combine(date, datetime.time(12)), True)
        if shift and shift.get("end_datetime"):
            return get_datetime(shift.end_datetime)

    return fixed
