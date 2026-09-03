import tkinter as tk
import unittest

from backend.i18n import Translator
from frontend.gui import MessageGroupWidgets, WhatsAppSchedulerApp


class _FakeVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


class _FakeEntry:
    def __init__(self, value):
        self._value = value

    def get(self, *_args, **_kwargs):
        return self._value


def _make_widgets(rows: list[dict]) -> MessageGroupWidgets:
    return MessageGroupWidgets(
        entries_contact=[_FakeEntry(r.get("contact", "")) for r in rows],
        entries_message=[_FakeEntry(r.get("message", "")) for r in rows],
        entries_date=[_FakeEntry(r.get("date", "")) for r in rows],
        listbox_hour=[_FakeEntry(r.get("hour", "")) for r in rows],
        listbox_minute=[_FakeEntry(r.get("minute", "")) for r in rows],
        listbox_ampm=[_FakeEntry(r.get("ampm", "")) for r in rows],
        send_vars=[_FakeVar(r.get("send", True)) for r in rows],
        repeat_vars=[_FakeEntry(r.get("repeat", "Ninguno")) for r in rows],
        days_vars=[[] for _ in rows],
        auto_label_vars=[_FakeVar(False) for _ in rows],
        auto_label_text_vars=[_FakeVar("") for _ in rows],
    )


class ScheduleMessagesGroupTests(unittest.TestCase):
    def _make_app(self) -> WhatsAppSchedulerApp:
        app = WhatsAppSchedulerApp.__new__(WhatsAppSchedulerApp)
        app.i18n = Translator("es")
        app.update_status = lambda *_args, **_kwargs: None
        return app

    def test_invalid_row_is_skipped_without_discarding_valid_siblings(self) -> None:
        # Regression test: a single malformed row inside a group tab (missing
        # hour, or an unparseable date) used to make _schedule_messages_group
        # `return []`, silently dropping every already-valid message in that
        # SAME tab. Now it must only skip the bad row.
        app = self._make_app()
        widgets = _make_widgets(
            [
                {"contact": "Alice", "message": "Hi", "date": "2099-01-01", "hour": "10", "minute": "00", "ampm": "AM"},
                {"contact": "Bob", "message": "Hi2", "date": "2099-01-01", "hour": "", "minute": "00", "ampm": "AM"},
                {"contact": "Carol", "message": "Hi3", "date": "not-a-date", "hour": "10", "minute": "00", "ampm": "AM"},
                {"contact": "Dave", "message": "Hi4", "date": "2099-01-01", "hour": "11", "minute": "30", "ampm": "PM"},
            ]
        )

        result = app._schedule_messages_group("Grupo 2", widgets, 2)

        contacts = [m["contact"] for m in result]
        self.assertEqual(contacts, ["Alice", "Dave"])

    def test_all_valid_rows_are_scheduled(self) -> None:
        app = self._make_app()
        widgets = _make_widgets(
            [
                {"contact": "Scheyla Mirella", "message": "Uno", "date": "2099-01-01", "hour": "10", "minute": "20", "ampm": "AM"},
                {"contact": "Scheyla Mirella", "message": "Dos", "date": "2099-01-01", "hour": "11", "minute": "17", "ampm": "AM"},
            ]
        )

        result = app._schedule_messages_group("Grupo 2", widgets, 2)

        self.assertEqual(len(result), 2)
        self.assertTrue(all(m["contact"] == "Scheyla Mirella" for m in result))

    def test_unchecked_row_is_skipped_silently(self) -> None:
        app = self._make_app()
        widgets = _make_widgets(
            [
                {"contact": "Alice", "message": "Hi", "date": "2099-01-01", "hour": "10", "minute": "00", "ampm": "AM", "send": False},
            ]
        )

        result = app._schedule_messages_group("Grupo 2", widgets, 2)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
