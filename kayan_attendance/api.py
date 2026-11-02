import frappe
from frappe import _
from frappe.utils import format_datetime, getdate, now_datetime

from kayan_attendance.attendance_watchdog import get_open_sessions, get_settings
from kayan_attendance.attendance_watchdog import run as run_watchdog

MANAGER_ROLES = ("System Manager", "HR Manager", "HR User")


def check_app_permission():
    if frappe.session.user == "Administrator":
        return True
    return bool(set(MANAGER_ROLES) & set(frappe.get_roles()))


def get_session_employee():
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"})
    if not employee:
        frappe.throw(_("No active Employee is linked to your user."), frappe.PermissionError)
    return employee


@frappe.whitelist()
def get_checkout_status(employee: str | None = None) -> dict:
    """The employee's open check-in, if any, and when the watchdog will check them out.

    For any mobile client; the Frappe HR app itself only needs the Employee Checkin list.
    """
    employee = employee or get_session_employee()
    frappe.has_permission("Employee", "read", employee, throw=True)

    sessions = [s for s in get_open_sessions(get_settings(), now_datetime(), employee) if s.checkout_time]
    if not sessions:
        return {"open": False}

    session = sessions[-1]
    return {
        "open": True,
        "check_in": session.name,
        "check_in_time": session.time,
        "planned_checkout": session.checkout_time,
        "planned_checkout_label": format_datetime(session.checkout_time, "HH:mm"),
        "rule": session.rule,
        "extension": session.extension,
    }


@frappe.whitelist(methods=["POST"])
def request_extension(extended_until: str, reason: str | None = None, date: str | None = None) -> str:
    """Ask for a later automatic check-out today (or on `date`) for the session user's employee."""
    if not frappe.db.get_single_value("Kayan Attendance Settings", "allow_extensions"):
        frappe.throw(_("Check-in time extensions are turned off."))

    extension = frappe.get_doc(
        {
            "doctype": "Checkin Time Extension",
            "employee": get_session_employee(),
            "date": getdate(date) if date else getdate(),
            "extended_until": extended_until,
            "reason": reason,
            "source": "API",
        }
    )
    extension.insert()
    return extension.name


@frappe.whitelist(methods=["POST"])
def run_watchdog_now() -> dict:
    frappe.only_for(MANAGER_ROLES)
    return run_watchdog() or {}
