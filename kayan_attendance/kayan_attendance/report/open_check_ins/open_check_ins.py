# Copyright (c) 2026, Nest Software Development and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

from kayan_attendance.attendance_watchdog import get_open_sessions, get_settings


def execute(filters=None):
    filters = frappe._dict(filters or {})
    settings = get_settings()
    now = now_datetime()

    sessions = get_open_sessions(settings, now, filters.employee)
    if filters.department:
        in_department = set(frappe.get_all("Employee", {"department": filters.department}, pluck="name"))
        sessions = [s for s in sessions if s.employee in in_department]

    data = []
    for session in sessions:
        if session.checkout_time is None:
            status = _("Not Closable")
        elif now >= add_to_date(session.checkout_time, minutes=cint(settings.grace_minutes)):
            status = _("Due")
        else:
            status = _("Checked In")
        data.append(
            {
                "employee": session.employee,
                "employee_name": session.employee_name,
                "check_in": session.name,
                "check_in_time": session.time,
                "planned_checkout": session.checkout_time,
                "rule": session.rule,
                "extension": session.extension,
                "status": status,
            }
        )

    return get_columns(), data


def get_columns():
    return [
        {
            "label": _("Employee"),
            "fieldname": "employee",
            "fieldtype": "Link",
            "options": "Employee",
            "width": 140,
        },
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
        {
            "label": _("Check-in"),
            "fieldname": "check_in",
            "fieldtype": "Link",
            "options": "Employee Checkin",
            "width": 150,
        },
        {"label": _("Check-in Time"), "fieldname": "check_in_time", "fieldtype": "Datetime", "width": 170},
        {
            "label": _("Planned Check-out"),
            "fieldname": "planned_checkout",
            "fieldtype": "Datetime",
            "width": 170,
        },
        {"label": _("Rule"), "fieldname": "rule", "fieldtype": "Data", "width": 110},
        {
            "label": _("Extension"),
            "fieldname": "extension",
            "fieldtype": "Link",
            "options": "Checkin Time Extension",
            "width": 150,
        },
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
    ]
