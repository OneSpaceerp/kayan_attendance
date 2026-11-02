# Copyright (c) 2026, Nest Software Development and contributors
# For license information, please see license.txt

import datetime

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, cint, flt, format_time, get_time, getdate

from kayan_attendance.attendance_watchdog import (
    create_app_notification,
    get_normal_checkout_time,
    get_settings,
)

APPROVER_ROLES = ("System Manager", "HR Manager", "HR User")


class CheckinTimeExtension(Document):
    def validate(self):
        from hrms.hr.utils import validate_active_employee

        validate_active_employee(self.employee)
        self.validate_owner_employee()
        self.set_approver()
        self.validate_duplicate()
        self.validate_extended_until()

    def on_update(self):
        self.share_with_approver()

    def after_insert(self):
        settings = get_settings()
        if cint(settings.notify_approver) and self.approver and self.approver != frappe.session.user:
            create_app_notification(
                self.approver,
                _("{0} asks to stay checked in until {1} on {2}.").format(
                    frappe.bold(self.employee_name),
                    format_time(self.extended_until, "HH:mm"),
                    frappe.format(self.date, "Date"),
                ),
                self.doctype,
                self.name,
            )

    def on_submit(self):
        if self.status not in ("Approved", "Rejected"):
            frappe.throw(
                _("Only Check-in Time Extensions with status Approved or Rejected can be submitted.")
            )
        self.validate_approver()
        self.notify_employee()

    def on_cancel(self):
        self.db_set("status", "Cancelled")

    def validate_owner_employee(self):
        if self.flags.ignore_permissions or can_approve_any():
            return
        user = frappe.session.user
        if frappe.db.get_value("Employee", self.employee, "user_id") != user and self.approver != user:
            frappe.throw(_("You can only request an extension for yourself."), frappe.PermissionError)

    def set_approver(self):
        if not self.approver:
            self.approver = get_extension_approver(self.employee)

    def validate_duplicate(self):
        duplicate = frappe.db.exists(
            "Checkin Time Extension",
            {
                "employee": self.employee,
                "date": self.date,
                "docstatus": ("<", 2),
                "status": ("in", ("Open", "Approved")),
                "name": ("!=", self.name),
            },
        )
        if duplicate and self.status in ("Open", "Approved"):
            frappe.throw(
                _("{0} already has a Check-in Time Extension for {1}: {2}").format(
                    self.employee_name or self.employee,
                    frappe.format(self.date, "Date"),
                    frappe.get_desk_link(self.doctype, duplicate),
                )
            )

    def validate_extended_until(self):
        settings = get_settings()
        if not cint(settings.allow_extensions):
            frappe.throw(_("Check-in time extensions are turned off in Kayan Attendance Settings."))

        normal = get_normal_checkout_time(self.employee, self.date, settings)
        extended = datetime.datetime.combine(getdate(self.date), get_time(self.extended_until))
        self.normal_checkout_time = normal

        if extended <= normal and self.source != "Re-check-in":
            frappe.throw(
                _("Extended Until must be later than the normal check-out time, {0}.").format(
                    normal.strftime("%H:%M")
                )
            )

        max_hours = flt(settings.max_extension_hours)
        if max_hours and extended > add_to_date(normal, hours=max_hours):
            frappe.throw(
                _("An extension can last at most {0} hours after {1}.").format(
                    frappe.format(max_hours, "Float"), normal.strftime("%H:%M")
                )
            )

    def share_with_approver(self):
        # an approver with only the Employee role cannot see other employees' requests without a share
        if not self.approver or frappe.has_permission(doc=self, ptype="submit", user=self.approver):
            return
        frappe.share.add_docshare(
            self.doctype,
            self.name,
            self.approver,
            write=1,
            submit=1,
            flags={"ignore_share_permission": True},
        )

    def validate_approver(self):
        if self.flags.ignore_permissions or can_approve_any():
            return
        if frappe.session.user not in get_extension_approvers(self.employee):
            frappe.throw(_("Only the employee's shift request approver or HR can approve this request."))

    def notify_employee(self):
        if not cint(get_settings().notify_employee):
            return
        user = frappe.db.get_value("Employee", self.employee, "user_id")
        if not user:
            return
        if self.status == "Approved":
            message = _("Your check-in time on {0} is extended until {1}.").format(
                frappe.format(self.date, "Date"), format_time(self.extended_until, "HH:mm")
            )
        else:
            message = _("Your check-in time extension for {0} was rejected.").format(
                frappe.format(self.date, "Date")
            )
        create_app_notification(user, message, self.doctype, self.name)


def can_approve_any():
    return bool(set(APPROVER_ROLES) & set(frappe.get_roles()))


def get_extension_approvers(employee):
    """Same approvers as an HRMS Shift Request: the employee's and the department's, plus the manager."""
    shift_approver, department, reports_to = frappe.db.get_value(
        "Employee", employee, ["shift_request_approver", "department", "reports_to"]
    )
    approvers = [shift_approver] if shift_approver else []
    if department:
        approvers += frappe.get_all(
            "Department Approver",
            filters={"parent": department, "parentfield": "shift_request_approver"},
            order_by="idx asc",
            pluck="approver",
        )
    if reports_to and (manager := frappe.db.get_value("Employee", reports_to, "user_id")):
        approvers.append(manager)
    return [a for a in approvers if a]


def get_extension_approver(employee):
    approvers = get_extension_approvers(employee)
    return approvers[0] if approvers else None
