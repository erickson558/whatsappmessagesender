import unittest

from backend.browser_worker import BrowserWorker


class _FakeKeyboard:
    def press(self, _key):
        pass


class _FakeMouse:
    def click(self, _x, _y):
        pass


class _FakePage:
    def __init__(self):
        self.keyboard = _FakeKeyboard()
        self.mouse = _FakeMouse()

    def wait_for_timeout(self, _ms):
        pass


class _FakeNode:
    def scroll_into_view_if_needed(self, timeout=0):
        pass

    def click(self, timeout=0, force=False):
        pass


def _make_worker(active_chat_name: str, candidate_name: str, compose_visible: bool = True) -> BrowserWorker:
    """Builds a BrowserWorker where every earlier _select_contact strategy
    (already-in-chat check, keyboard, JS-locate + mouse.click) has been made
    to fail on purpose, forcing execution into Estrategia 3's ranked-candidate
    loop -- the only place the new self-consistency fallback lives.
    """
    worker = BrowserWorker.__new__(BrowserWorker)
    worker.page = _FakePage()
    worker.log = lambda *_a, **_k: None
    worker.status = lambda *_a, **_k: None
    worker._ensure_browser = lambda: True
    worker._is_in_chat = lambda _contact: False
    worker._is_search_active = lambda: False
    worker._focus_global_search = lambda: object()
    worker._type_search_variants = lambda _contact: None
    worker._click_contact_js = lambda _contact: None
    # Every strict contact-name check fails, mirroring a WhatsApp display name
    # (nickname/push-name) that never contains all tokens of the configured contact.
    worker._wait_header = lambda *_a, **_k: False
    worker._collect_candidates = lambda: []
    worker._rank_candidates = lambda _contact, _candidates: [(1.0, "row", candidate_name, _FakeNode(), 0)]
    worker._clear_global_search = lambda: None
    worker._get_active_chat_from_composer = lambda: active_chat_name
    worker._is_compose_visible = lambda: compose_visible
    return worker


class BrowserWorkerPartialNameMatchTests(unittest.TestCase):
    def test_self_consistent_candidate_name_is_accepted_despite_shortened_display_name(self) -> None:
        # "Scheyla Mirella" is configured, but WhatsApp displays the chat under
        # a shortened name ("Scheyla") that _like_match(contact, ...) can never
        # satisfy (missing the "Mirella" token). The candidate row we ourselves
        # ranked and clicked was also labeled "Scheyla", and the chat that ends
        # up active after the click reports that same "Scheyla" -- self-consistent.
        worker = _make_worker(active_chat_name="Scheyla", candidate_name="Scheyla", compose_visible=True)

        self.assertTrue(worker._select_contact("Scheyla Mirella"))

    def test_mismatched_active_chat_after_click_is_not_accepted(self) -> None:
        # The candidate we clicked was labeled "Scheyla", but somehow a totally
        # different chat ("Juan Perez") ended up active. This must NOT be
        # accepted -- the self-consistency fallback must not degrade into a
        # generic "any open chat with a visible composer" acceptance, which is
        # exactly the cross-contact leakage bug V8.9.13 fixed.
        worker = _make_worker(active_chat_name="Juan Perez", candidate_name="Scheyla", compose_visible=True)

        self.assertFalse(worker._select_contact("Scheyla Mirella"))


if __name__ == "__main__":
    unittest.main()
