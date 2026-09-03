import time
import unittest

from backend.browser_worker import BrowserWorker


class _FakePage:
    def wait_for_timeout(self, ms: int) -> None:
        time.sleep(min(ms, 10) / 1000.0)


class BrowserWorkerContactTargetingTests(unittest.TestCase):
    def _make_worker(self) -> BrowserWorker:
        worker = BrowserWorker.__new__(BrowserWorker)
        worker.page = _FakePage()
        worker.log = lambda *_args, **_kwargs: None
        worker.status = lambda *_args, **_kwargs: None
        return worker

    def test_wait_header_requires_contact_match_before_accepting_compose(self) -> None:
        worker = self._make_worker()
        worker._is_in_chat = lambda _contact: False
        worker._is_compose_visible = lambda: True

        self.assertFalse(worker._wait_header("Alice", timeout_ms=80, require_compose=True))

    def test_wait_header_accepts_target_when_contact_and_compose_match(self) -> None:
        worker = self._make_worker()
        worker._is_in_chat = lambda contact: contact == "Alice"
        worker._is_compose_visible = lambda: True

        self.assertTrue(worker._wait_header("Alice", timeout_ms=80, require_compose=True))

    def test_ensure_chat_target_retries_when_foreign_chat_keeps_compose_visible(self) -> None:
        worker = self._make_worker()
        worker._is_in_chat = lambda _contact: False
        worker._is_compose_visible = lambda: True
        worker._get_active_chat_from_composer = lambda: "Bob"
        attempts: list[str] = []

        def _select_contact(contact: str) -> bool:
            attempts.append(contact)
            return False

        worker._select_contact = _select_contact

        self.assertFalse(worker._ensure_chat_target("Alice", attempts=2))
        self.assertEqual(attempts, ["Alice", "Alice"])


if __name__ == "__main__":
    unittest.main()
