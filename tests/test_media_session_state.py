"""Parse numeric and named Android media-session playback states."""

import json
from pathlib import Path
import unittest

from androidtv.androidtv.base_androidtv import BaseAndroidTV


STATES = (
    "NONE",
    "STOPPED",
    "PAUSED",
    "PLAYING",
    "FAST_FORWARDING",
    "REWINDING",
    "BUFFERING",
    "ERROR",
    "CONNECTING",
    "SKIPPING_TO_PREVIOUS",
    "SKIPPING_TO_NEXT",
    "SKIPPING_TO_QUEUE_ITEM",
)


class TestMediaSessionState(unittest.TestCase):
    def setUp(self):
        self.tv = BaseAndroidTV("unused-offline-host")

    def parse(self, state):
        return self.tv._current_app_media_session_state(
            "com.example.player\nstate=PlaybackState {state=" + state + ", position=123, speed=1.0}\n"
        )

    def test_legacy_numeric_states(self):
        for code in range(len(STATES)):
            with self.subTest(code=code):
                self.assertEqual(self.parse(str(code)), ("com.example.player", code))

    def test_named_states(self):
        for code, name in enumerate(STATES):
            with self.subTest(name=name):
                self.assertEqual(self.parse("{}({})".format(name, code)), ("com.example.player", code))

    def test_unknown_named_state_keeps_numeric_code(self):
        self.assertEqual(self.parse("UNKNOWN(42)"), ("com.example.player", 42))

    def test_malformed_states_are_unknown(self):
        for value in ("", "PLAYING", "PLAYING()", "PLAYING(3", "PLAYING(3x)", "3x", "3)", "(3)"):
            with self.subTest(value=value):
                self.assertEqual(self.parse(value), ("com.example.player", None))

    def test_existing_custom_numeric_reply(self):
        self.assertEqual(
            self.tv._current_app_media_session_state("com.example.player\nstate=3"),
            ("com.example.player", 3),
        )

    def test_recorded_google_tv_replies(self):
        fixture = json.loads((Path(__file__).with_name("fixtures") / "google_tv_playback.json").read_text())
        for name, sample in fixture["samples"].items():
            with self.subTest(capture=name):
                reply = sample["expected_app"] + "\n" + sample["media"]
                self.assertEqual(
                    self.tv._current_app_media_session_state(reply),
                    (sample["expected_app"], sample["expected_media_session_state"]),
                )

    def test_missing_reply_does_not_invent_state(self):
        for reply in (None, "", "com.example.player"):
            with self.subTest(reply=reply):
                expected = "com.example.player" if reply else None
                self.assertEqual(self.tv._current_app_media_session_state(reply), (expected, None))
