# Copyright (c) 2026, Nest Software Development and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import cint, flt


class KayanAttendanceSettings(Document):
    def validate(self):
        self.lookback_days = max(cint(self.lookback_days), 1)
        self.grace_minutes = max(cint(self.grace_minutes), 0)
        for fieldname in ("late_session_hours", "default_extension_hours", "max_extension_hours"):
            self.set(fieldname, max(flt(self.get(fieldname)), 0))
