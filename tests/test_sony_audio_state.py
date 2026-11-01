"""Sony Android 10 audio regression tests using recorded and synthetic replies."""
import copy
import json
from pathlib import Path
import unittest

from androidtv import constants
from . import test_sony_android10 as replay


AUDIO = json.loads((Path(__file__).parent / "fixtures" / "sony_android10_audio.json").read_text())["samples"]


class TestSonyAudioState(unittest.TestCase):
    """Exercise real audio-query shell commands, parsers and state selection."""

    def setUp(self):
        self.harness = replay.TestSonyAndroid10()
        self.harness.setUp()
        self.tv = self.harness.tv

    def query(self, sample, audio_rc=0, packages_rc=0):
        """Replay the recorded or synthetic replies labelled by each fixture."""
        fixture = {
            "window": sample.get("window", replay.FIXTURES["tivimate"]["window"]),
            "activity": sample["activity"],
        }
        result, calls = self.harness.run_query(
            self.tv._cmd_audio_state(),
            fixture,
            audio=sample["audio"],
            packages=sample["packages"],
            audio_rc=audio_rc,
            packages_rc=packages_rc,
        )
        self.assertEqual(result.stderr, "")
        return self.tv._audio_state(result.stdout.strip()), calls

    def update_state(self, state, app="ar.tvplayer.tv", session=None, wake_locks=2):
        """Use the actual normal update policy, not just the audio parser."""
        return self.tv._update(True, True, state, wake_locks, app, session, "speaker", False, 10, [app], None)[0]

    def test_recorded_playing(self):
        state, _ = self.query(AUDIO["playing"])
        self.assertEqual(state, constants.STATE_PLAYING)
        self.assertEqual(self.update_state(state), constants.STATE_PLAYING)

    def test_recorded_paused(self):
        state, _ = self.query(AUDIO["paused"])
        self.assertEqual(state, constants.STATE_PAUSED)
        self.assertEqual(self.update_state(state), constants.STATE_PAUSED)

    def test_recorded_resumed(self):
        state, _ = self.query(AUDIO["resumed"])
        self.assertEqual(state, constants.STATE_PLAYING)
        self.assertEqual(self.update_state(state), constants.STATE_PLAYING)

    def test_recorded_settings_has_no_media_player(self):
        state, _ = self.query(AUDIO["settings"])
        self.assertEqual(state, constants.STATE_IDLE)
        for locks in (1, 2, 9):
            with self.subTest(wake_locks=locks):
                self.assertEqual(
                    self.update_state(state, app="com.android.tv.settings", wake_locks=locks), constants.STATE_IDLE
                )

    def test_recorded_home_preview_is_idle(self):
        """The recorded launcher has started media, but is still a menu."""
        state, calls = self.query(AUDIO["home"])
        self.assertEqual(state, constants.STATE_IDLE)
        self.assertEqual(self.update_state(state, app=AUDIO["home"]["app"]), constants.STATE_IDLE)
        self.assertNotIn("dumpsys audio", calls)

    def test_recorded_standby_has_no_app(self):
        state, calls = self.query(AUDIO["final_standby"])
        self.assertEqual(state, constants.STATE_IDLE)
        self.assertNotIn("dumpsys audio", calls)
        self.assertFalse(any(call.startswith("cmd package ") for call in calls))

    def test_synthetic_history_cannot_override_current_player(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] += (
            "\nAudio event log: playback activity as reported through PlayerBase\n"
            "10-31 22:44:09:663 player piid:527 state:paused\n"
            "10-31 22:45:33:488 player piid:527 state:stopped\n"
        )
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_PLAYING)

    def test_synthetic_large_history_does_not_corrupt_output(self):
        """Read the full dump without an early-exit pipe contaminating stdout."""
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] += "\nAudio event log:\n" + "10-31 22:44:09:663 player piid:527 state:paused\n" * 1500
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_PLAYING)

    def test_synthetic_old_started_event_does_not_mean_playing(self):
        sample = copy.deepcopy(AUDIO["paused"])
        sample["audio"] += "\nAudio event log:\n10-31 22:42:07:704 player piid:527 state:started\n"
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_PAUSED)

    def test_synthetic_history_only_is_idle(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = (
            "PlaybackActivityMonitor dump time: synthetic\n  players:\n  ducked players piids:\n"
            "Audio event log:\n"
            "ID:123 -- u/pid:10208/1 -- state:started -- usage=USAGE_MEDIA content=CONTENT_TYPE_MOVIE\n"
        )
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)
        self.assertEqual(self.update_state(state), constants.STATE_IDLE)

    def test_synthetic_background_player_is_ignored(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].replace("u/pid:10208/", "u/pid:99999/")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)

    def test_synthetic_uid_prefix_collision_is_ignored(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].replace("u/pid:10208/", "u/pid:110208/")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)

    def test_synthetic_navigation_sound_is_ignored(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].replace("usage=USAGE_MEDIA", "usage=USAGE_ASSISTANCE_SONIFICATION")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)

    def test_synthetic_stopped_track_is_idle(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].replace("state:started", "state:stopped")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)
        self.assertEqual(self.update_state(state), constants.STATE_IDLE)

    def test_synthetic_started_track_wins_over_paused_track(self):
        sample = copy.deepcopy(AUDIO["playing"])
        started = next(line for line in sample["audio"].splitlines() if "u/pid:10208/" in line)
        paused = started.replace("ID:607", "ID:999").replace("state:started", "state:paused")
        sample["audio"] = sample["audio"].replace(started, paused + "\n" + started)
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_PLAYING)

    def test_synthetic_missing_uid_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["packages"] = ""
        state, calls = self.query(sample)
        self.assertIsNone(state)
        self.assertNotIn("dumpsys audio", calls)

    def test_synthetic_malformed_uid_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["packages"] = "package:ar.tvplayer.tv uid:invalid\n"
        state, _ = self.query(sample)
        self.assertIsNone(state)

    def test_synthetic_missing_audio_section_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = "Audio server unavailable\n"
        state, _ = self.query(sample)
        self.assertIsNone(state)

    def test_synthetic_failed_audio_dump_is_unknown(self):
        state, _ = self.query(AUDIO["playing"], audio_rc=1)
        self.assertIsNone(state)

    def test_synthetic_google_launcher_preview_is_idle(self):
        sample = copy.deepcopy(AUDIO["home"])
        sample["activity"] = sample["activity"].replace(
            "com.google.android.tvlauncher", "com.google.android.apps.tv.launcherx"
        )
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)

    def test_valid_media_session_keeps_priority(self):
        for session, expected in ((1, constants.STATE_IDLE), (2, constants.STATE_PAUSED), (3, constants.STATE_PLAYING)):
            with self.subTest(session=session):
                self.assertEqual(
                    self.update_state(constants.STATE_IDLE, app=constants.APP_NETFLIX, session=session), expected
                )

    def test_empty_media_session_can_use_current_audio(self):
        self.assertEqual(self.update_state(constants.STATE_PLAYING, session=0), constants.STATE_PLAYING)

    def test_user_state_rules_keep_priority(self):
        self.tv._state_detection_rules = {"ar.tvplayer.tv": ["paused"]}
        self.assertEqual(self.update_state(constants.STATE_PLAYING), constants.STATE_PAUSED)

    def test_custom_audio_command_keeps_priority(self):
        self.tv.customize_command(constants.CUSTOM_AUDIO_STATE, "printf 2")
        self.assertEqual(self.tv._cmd_audio_state(), "printf 2")

    def test_other_devices_keep_audio_query_selection(self):
        for manufacturer, version, expected in (
            ("Sony", "9", constants.CMD_AUDIO_STATE),
            ("Sony", "11", constants.CMD_AUDIO_STATE11),
            ("Google", "14", constants.CMD_AUDIO_STATE11),
            ("Other", "10", constants.CMD_AUDIO_STATE),
        ):
            with self.subTest(manufacturer=manufacturer, version=version):
                self.tv.device_properties = {"manufacturer": manufacturer, "sw_version": version}
                self.assertEqual(self.tv._cmd_audio_state(), expected)

    def test_failed_package_lookup_does_not_use_partial_stdout(self):
        state, calls = self.query(AUDIO["playing"], packages_rc=1)
        self.assertIsNone(state)
        self.assertNotIn("dumpsys audio", calls)

    def test_partial_audio_dump_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].split("  ducked players")[0]
        state, _ = self.query(sample)
        self.assertIsNone(state)

    def test_audio_section_without_player_list_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = "PlaybackActivityMonitor dump time: synthetic\n  ducked players piids:\n"
        state, _ = self.query(sample)
        self.assertIsNone(state)

    def test_uid_with_trailing_garbage_is_unknown(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["packages"] = "package:ar.tvplayer.tv uid:10208invalid\n"
        state, _ = self.query(sample)
        self.assertIsNone(state)

    def assert_recorded_playback(self, prefix):
        """Replay real app/audio/session replies through the normal state policy."""
        samples = json.loads((Path(__file__).parent / "fixtures" / "sony_android10_playback.json").read_text())[
            "samples"
        ]
        for phase, sample in samples.items():
            if not phase.startswith(prefix):
                continue
            with self.subTest(phase=phase):
                audio, _ = self.query(sample)
                self.assertEqual(audio, sample["expected_audio"])
                result, _ = self.harness.run_query(
                    self.tv._cmd_current_app_media_session_state(), sample, media=sample["media"]
                )
                self.assertEqual(result.stderr, "")
                app, session = self.tv._current_app_media_session_state(result.stdout)
                self.assertEqual((app, session), (sample["expected_app"], sample["expected_session"]))
                update = self.tv._update(
                    sample["screen_on"],
                    sample["awake"],
                    audio,
                    sample["wake_locks"],
                    app,
                    session,
                    "speaker",
                    False,
                    10,
                    [app] if app else None,
                    None,
                )
                self.assertEqual(update[0], sample["expected_state"])

    def test_recorded_youtube_playback(self):
        self.assert_recorded_playback("youtube")

    def test_recorded_angel_program_playback(self):
        self.assert_recorded_playback("angel")

    def test_recorded_tivimate_after_app_switches(self):
        self.assert_recorded_playback("tivimate")

    def test_recorded_home_settings_and_standby(self):
        for prefix in ("home", "settings", "standby"):
            self.assert_recorded_playback(prefix)

    def test_player_tags_cannot_override_paused_state(self):
        sample = copy.deepcopy(AUDIO["paused"])
        sample["audio"] = sample["audio"].replace("tags= bundle", "tags=state:started  bundle")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_PAUSED)

    def test_navigation_player_tag_is_not_media_usage(self):
        sample = copy.deepcopy(AUDIO["playing"])
        sample["audio"] = sample["audio"].replace("usage=USAGE_MEDIA", "usage=USAGE_ASSISTANCE_SONIFICATION")
        sample["audio"] = sample["audio"].replace("tags= bundle", "tags=usage=USAGE_MEDIA  bundle")
        state, _ = self.query(sample)
        self.assertEqual(state, constants.STATE_IDLE)


if __name__ == "__main__":
    unittest.main()
