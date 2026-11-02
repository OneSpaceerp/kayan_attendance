import frappe
from frappe.custom.doctype.custom_field.custom_field import (
    create_custom_fields as _create_custom_fields,
)

from kayan_attendance.constants.custom_fields import CUSTOM_FIELDS


def after_install():
    """Runs after install and after every migrate; every step is idempotent."""
    create_custom_fields()
    set_default_settings()


def create_custom_fields():
    _create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def set_default_settings():
    # Single doctypes keep defaults only once a value is saved; fill the ones the watchdog reads
    if not frappe.db.exists("DocType", "Kayan Attendance Settings"):
        return

    defaults = {
        "enable_watchdog": 1,
        "auto_checkout_time": "17:00:00",
        "checkout_time_based_on": "Fixed Time",
        "lookback_days": 3,
        "late_session_hours": 2,
        "allow_extensions": 1,
        "default_extension_hours": 2,
        "max_extension_hours": 4,
        "request_extension_on_recheckin": 1,
        "notify_employee": 1,
        "notify_approver": 1,
    }
    current = frappe.db.get_singles_dict("Kayan Attendance Settings")
    for fieldname, value in defaults.items():
        if current.get(fieldname) is None:
            frappe.db.set_single_value("Kayan Attendance Settings", fieldname, value)
