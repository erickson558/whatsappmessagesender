import threading
import unittest
from datetime import datetime, timedelta

from backend.i18n import Translator
from frontend.gui import WhatsAppSchedulerApp


class _FakeBackend:
    def __init__(self):
        self._delivery_lock = threading.Lock()
        self.sent = []

    def bind_whatsapp_tab(self):
        return True

    def select_contact(self, _contact):
        return True

    def send_message(self, text, contact):
        self.sent.append((contact, text))
        return True


class GroupDayFilterTests(unittest.TestCase):
    def _make_app(self) -> WhatsAppSchedulerApp:
        app = WhatsAppSchedulerApp.__new__(WhatsAppSchedulerApp)
        app.i18n = Translator("es")
        app.update_status = lambda *_args, **_kwargs: None
        app.backend = _FakeBackend()
        app._scheduled_calls = []
        app._schedule_message = lambda item: app._scheduled_calls.append(item)
        return app

    def test_not_due_sibling_is_untouched_when_container_fires_for_due_item(self) -> None:
        # Regression test: two items scheduled for the same contact at the same
        # time land in one "is_group" container. Firing the container for a due
        # item used to also clobber a NOT-yet-due, days-restricted sibling's
        # datetime with datetime.now() + delta, discarding its own configured
        # date/time. It must now be rescheduled untouched instead.
        app = self._make_app()
        now = datetime.now()
        other_day = (now.weekday() + 3) % 7

        due_item = {
            "contact": "Scheyla Mirella",
            "message": "Uno",
            "datetime": now - timedelta(seconds=5),
            "repeat": "Ninguno",
            "days": [],
            "last_sent": None,
        }
        future_item_original_dt = now + timedelta(days=10)
        future_restricted_item = {
            "contact": "Scheyla Mirella",
            "message": "Dos",
            "datetime": future_item_original_dt,
            "repeat": "Mensualmente",
            "days": [other_day],
            "last_sent": None,
        }

        container = {
            "is_group": True,
            "contact": "Scheyla Mirella",
            "datetime": due_item["datetime"],
            "items": [due_item, future_restricted_item],
        }

        app._process_scheduled_message(container)

        self.assertEqual(future_restricted_item["datetime"], future_item_original_dt)
        self.assertIn(future_restricted_item, app._scheduled_calls)
        self.assertEqual(app.backend.sent, [("Scheyla Mirella", "Uno")])

    def test_due_item_failing_day_filter_preserves_its_configured_time_of_day(self) -> None:
        # Regression test: rescheduling a due item to the next allowed weekday
        # must preserve its own hour/minute, not adopt whatever wall-clock time
        # the container happened to fire at.
        app = self._make_app()
        now = datetime.now()
        other_day = (now.weekday() + 3) % 7
        original_time = now.replace(hour=14, minute=30, second=0, microsecond=0) - timedelta(days=1)

        item = {
            "contact": "Scheyla Mirella",
            "message": "Uno",
            "datetime": original_time,
            "repeat": "Mensualmente",
            "days": [other_day],
            "last_sent": None,
        }
        container = {
            "is_group": True,
            "contact": "Scheyla Mirella",
            "datetime": item["datetime"],
            "items": [item],
        }

        app._process_scheduled_message(container)

        self.assertEqual(item["datetime"].time(), original_time.time())
        self.assertNotEqual(item["datetime"].date(), original_time.date())
        self.assertEqual(item["datetime"].weekday(), other_day)
        self.assertEqual(app.backend.sent, [])


if __name__ == "__main__":
    unittest.main()
