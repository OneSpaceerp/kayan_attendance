from datetime import datetime, time

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import add_days, getdate, now_datetime

from kayan_attendance.attendance_watchdog import (
    RULE_EXTENSION,
    RULE_FIXED_TIME,
    RULE_LATE_SESSION,
    RULE_SHIFT_END,
    get_open_sessions,
    get_settings,
    resolve_checkout_time,
)
from kayan_attendance.attendance_watchdog import run as run_watchdog


class TestResolveCheckoutTime(UnitTestCase):
    def test_fixed_time(self):
        self.assertEqual(
            resolve_checkout_time(datetime(2026, 11, 2, 8, 30), "17:00:00"),
            (datetime(2026, 11, 2, 17, 0), RULE_FIXED_TIME),
        )

    def test_shift_end(self):
        self.assertEqual(
            resolve_checkout_time(
                datetime(2026, 11, 2, 22, 0), "17:00:00", shift_end=datetime(2026, 11, 3, 6, 0)
            ),
            (datetime(2026, 11, 3, 6, 0), RULE_SHIFT_END),
        )

    def test_extension_only_lengthens(self):
        self.assertEqual(
            resolve_checkout_time(datetime(2026, 11, 2, 8, 0), "17:00:00", extended_until="19:30:00"),
            (datetime(2026, 11, 2, 19, 30), RULE_EXTENSION),
        )
        self.assertEqual(
            resolve_checkout_time(datetime(2026, 11, 2, 8, 0), "17:00:00", extended_until="16:00:00"),
            (datetime(2026, 11, 2, 17, 0), RULE_FIXED_TIME),
        )

    def test_late_session(self):
        self.assertEqual(
            resolve_checkout_time(datetime(2026, 11, 2, 18, 0), "17:00:00", late_session_hours=2),
            (datetime(2026, 11, 2, 20, 0), RULE_LATE_SESSION),
        )
        # never past midnight
        self.assertEqual(
            resolve_checkout_time(datetime(2026, 11, 2, 23, 0), "17:00:00", late_session_hours=2),
            (datetime(2026, 11, 2, 23, 59, 59), RULE_LATE_SESSION),
        )
        self.assertIsNone(resolve_checkout_time(datetime(2026, 11, 2, 18, 0), "17:00:00"))

    def test_never_after_next_check_in(self):
        self.assertEqual(
            resolve_checkout_time(
                datetime(2026, 11, 2, 8, 0),
                "17:00:00",
                next_check_in=datetime(2026, 11, 2, 13, 0),
            ),
            (datetime(2026, 11, 2, 12, 59, 59), RULE_FIXED_TIME),
        )


class TestAttendanceWatchdog(IntegrationTestCase):
    def setUp(self):
        self.employee = make_employee()
        frappe.db.delete("Employee Checkin", {"employee": self.employee})
        frappe.db.delete("Checkin Time Extension", {"employee": self.employee})
        frappe.db.delete("Attendance Watchdog Log", {"employee": self.employee})
        settings = frappe.get_single("Kayan Attendance Settings")
        settings.update(
            {
                "enable_watchdog": 1,
                "auto_checkout_time": "17:00:00",
                "checkout_time_based_on": "Fixed Time",
                "grace_minutes": 0,
                "lookback_days": 3,
                "allow_extensions": 1,
                "max_extension_hours": 4,
                "notify_employee": 0,
                "notify_approver": 0,
            }
        )
        settings.save()

    def test_open_check_in_of_yesterday_is_closed_at_17(self):
        yesterday = add_days(getdate(), -1)
        check_in = make_checkin(self.employee, "IN", f"{yesterday} 08:00:00")

        run_watchdog()

        checkout = frappe.get_all(
            "Employee Checkin",
            filters={"kayan_source_checkin": check_in},
            fields=["log_type", "time", "kayan_auto_checkout", "kayan_checkout_rule"],
        )
        self.assertEqual(len(checkout), 1)
        self.assertEqual(checkout[0].log_type, "OUT")
        self.assertEqual(checkout[0].time, datetime.combine(yesterday, time(17)))
        self.assertEqual(checkout[0].kayan_checkout_rule, RULE_FIXED_TIME)
        self.assertEqual(
            frappe.db.get_value("Attendance Watchdog Log", {"check_in": check_in}, "status"), "Success"
        )

        # a closed session is left alone on the next run
        run_watchdog()
        self.assertEqual(frappe.db.count("Employee Checkin", {"kayan_source_checkin": check_in}), 1)

    def test_closed_check_in_is_ignored(self):
        yesterday = add_days(getdate(), -1)
        make_checkin(self.employee, "IN", f"{yesterday} 08:00:00")
        make_checkin(self.employee, "OUT", f"{yesterday} 16:00:00")

        self.assertFalse(get_open_sessions(get_settings(), now_datetime(), self.employee))

    def test_approved_extension_moves_the_checkout(self):
        yesterday = add_days(getdate(), -1)
        check_in = make_checkin(self.employee, "IN", f"{yesterday} 08:00:00")
        extension = frappe.get_doc(
            {
                "doctype": "Checkin Time Extension",
                "employee": self.employee,
                "date": yesterday,
                "extended_until": "19:00:00",
                "status": "Approved",
            }
        ).insert()
        extension.submit()

        run_watchdog()

        checkout_time, rule = frappe.db.get_value(
            "Employee Checkin", {"kayan_source_checkin": check_in}, ["time", "kayan_checkout_rule"]
        )
        self.assertEqual(checkout_time, datetime.combine(yesterday, time(19)))
        self.assertEqual(rule, RULE_EXTENSION)

    def test_extension_over_the_limit_is_refused(self):
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc(
                {
                    "doctype": "Checkin Time Extension",
                    "employee": self.employee,
                    "date": getdate(),
                    "extended_until": "22:30:00",
                }
            ).insert()

    def test_recheckin_after_auto_checkout_requests_extension(self):
        frappe.db.set_single_value("Kayan Attendance Settings", "request_extension_on_recheckin", 1)
        yesterday = add_days(getdate(), -1)
        make_checkin(self.employee, "IN", f"{yesterday} 08:00:00")
        run_watchdog()

        # back at work after the 17:00 automatic check-out, as from the Frappe HR app
        make_checkin(self.employee, "IN", f"{yesterday} 17:30:00")

        extension = frappe.db.get_value(
            "Checkin Time Extension",
            {"employee": self.employee, "date": yesterday},
            ["status", "source", "extended_until"],
            as_dict=True,
        )
        self.assertEqual(extension.status, "Open")
        self.assertEqual(extension.source, "Re-check-in")
        self.assertEqual(str(extension.extended_until), "19:30:00")


def make_employee():
    name = frappe.db.get_value("Employee", {"first_name": "_Test Kayan Watchdog"})
    if name:
        return name
    return (
        frappe.get_doc(
            {
                "doctype": "Employee",
                "first_name": "_Test Kayan Watchdog",
                "gender": "Male",
                "date_of_birth": "1990-01-01",
                "date_of_joining": "2020-01-01",
                "company": frappe.get_all("Company", limit=1, pluck="name")[0],
                "status": "Active",
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def make_checkin(employee, log_type, timestamp):
    return (
        frappe.get_doc(
            {"doctype": "Employee Checkin", "employee": employee, "log_type": log_type, "time": timestamp}
        )
        .insert(ignore_permissions=True)
        .name
    )
