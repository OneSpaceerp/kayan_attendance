app_name = "kayan_attendance"
app_title = "Kayan Attendance"
app_publisher = "Nest Software Development"
app_description = "Attendance watchdog for Frappe HR: automatic check-out for open check-ins and check-in time extensions, in step with the Frappe HR mobile app"
app_email = "info@nsd-eg.com"
app_license = "GNU General Public License (v3)"

required_apps = ["frappe/erpnext", "frappe/hrms"]

app_logo_url = "/assets/kayan_attendance/images/kayan-attendance-logo.png"
app_home = "/desk/kayan-attendance"

add_to_apps_screen = [
    {
        "name": "kayan_attendance",
        "logo": "/assets/kayan_attendance/images/kayan-attendance-logo.png",
        "title": "Kayan Attendance",
        "route": app_home,
        "has_permission": "kayan_attendance.api.check_app_permission",
    }
]

# Frappe v16 dock and sidebar-header icons (kayan-attendance-*, kayan-setup-* in -duotone and -soft)
app_include_icons = ["/assets/kayan_attendance/icons/module-icons.svg"]

# Installation
# ------------
after_install = "kayan_attendance.setup.after_install"
after_migrate = "kayan_attendance.setup.after_install"

# Desk scripts on core doctypes
# -----------------------------
doctype_list_js = {"Employee Checkin": "public/js/employee_checkin_list.js"}

# Document Events
# ---------------
# Check-ins from the Frappe HR mobile app are plain inserts of Employee Checkin, so they arrive here.
doc_events = {
    "Employee Checkin": {
        "after_insert": "kayan_attendance.events.employee_checkin.after_insert",
    },
}

# Scheduled Tasks
# ---------------
# The watchdog runs every 10 minutes and closes each open check-in once its own check-out time has
# passed (the fixed time, the shift end or an approved extension), so 17:00 is honoured within minutes.
scheduler_events = {
    "cron": {
        "*/10 * * * *": ["kayan_attendance.attendance_watchdog.run"],
    },
}

# Testing
# -------
before_tests = "kayan_attendance.tests.test_utils.before_tests"
