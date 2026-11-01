"""Replay Sony Android 10 replies through real shell queries and library parsers.

The recorded cases are reduced snippets, not full dumps. Additional edge cases
are synthetic. No ADB transport is opened and no TV command is sent.
"""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from androidtv import constants
from androidtv.androidtv.base_androidtv import BaseAndroidTV
from androidtv.firetv.base_firetv import BaseFireTV


FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "sony_android10.json").read_text())

# These shell functions replay stdout; they never execute dumpsys or monkey.
SHELL_REPLAY = """
dumpsys() {
    printf '%s\\n' "dumpsys $*" >> "$REPLAY_CALLS"
    case "$*" in
        'window windows') printf '%s' "$REPLAY_WINDOW" ;;
        'activity activities')
            printf '%s' "$REPLAY_ACTIVITY_STDERR" >&2
            printf '%s' "$REPLAY_ACTIVITY" ;;
        'media_session') printf '%s' "$REPLAY_MEDIA_SESSION"; return "$REPLAY_MEDIA_RC" ;;
        'audio') printf '%s' "$REPLAY_AUDIO"; return "$REPLAY_AUDIO_RC" ;;
        *) printf 'Unexpected dumpsys query\\n' >&2; return 1 ;;
    esac
}
cmd() {
    printf '%s\\n' "cmd $*" >> "$REPLAY_CALLS"
    printf '%s' "$REPLAY_PACKAGES"
    return "$REPLAY_PACKAGES_RC"
}
monkey() {
    printf '%s\\n' "monkey $*" >> "$REPLAY_CALLS"
}
"""


class TestSonyAndroid10(unittest.TestCase):
    """Exercise the production command strings with deterministic input."""

    def setUp(self):
        self.tv = BaseAndroidTV("unused-offline-host")
        self.tv.device_properties = {
            "manufacturer": "Sony",
            "model": "BRAVIA 4K UR3",
            "sw_version": "10",
        }

    def run_query(
        self,
        command,
        fixture,
        media="",
        activity_stderr="",
        audio="",
        packages="",
        audio_rc=0,
        packages_rc=0,
        media_rc=0,
    ):
        """Run only local shell functions with recorded or synthetic replies."""
        with tempfile.TemporaryDirectory() as directory:
            calls_path = Path(directory) / "calls.txt"
            calls_path.touch()
            environment = os.environ.copy()
            environment.update(
                REPLAY_WINDOW=fixture["window"],
                REPLAY_ACTIVITY=fixture["activity"],
                REPLAY_ACTIVITY_STDERR=activity_stderr,
                REPLAY_MEDIA_SESSION=media,
                REPLAY_MEDIA_RC=str(media_rc),
                REPLAY_AUDIO=audio,
                REPLAY_AUDIO_RC=str(audio_rc),
                REPLAY_PACKAGES=packages,
                REPLAY_PACKAGES_RC=str(packages_rc),
                REPLAY_CALLS=str(calls_path),
            )
            result = subprocess.run(
                ["bash", "--posix", "-c", SHELL_REPLAY + command],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return result, calls_path.read_text().splitlines()

    def assert_recorded_app(self, name):
        """Interpret a recorded foreground-app reply with the library parser."""
        fixture = FIXTURES[name]
        result, calls = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(self.tv._current_app(result.stdout.strip()), fixture["expected"])
        self.assertIn("dumpsys activity activities", calls)

    def test_recorded_home(self):
        """The Home screen must resolve to the launcher package."""
        self.assert_recorded_app("home")

    def test_recorded_tivimate(self):
        """TiviMate must resolve to its package rather than a system window."""
        self.assert_recorded_app("tivimate")

    def test_recorded_settings(self):
        """Settings must resolve to its package."""
        self.assert_recorded_app("settings")

    def test_recorded_standby(self):
        """No resumed activity must remain an unknown app."""
        self.assert_recorded_app("standby")

    def test_pr357_reproduces_wrong_system_window(self):
        """Document why Window #1 is unsuitable on this recorded Sony."""
        command = constants.CMD_CURRENT_APP.replace("mCurrentFocus|mFocusedApp", "Window #1|mCurrentFocus|mFocusedApp")
        result, _ = self.run_query(command, FIXTURES["tivimate"])
        self.assertEqual(result.stdout.strip(), "DockedStackDivider")

    def test_legacy_focus_takes_priority(self):
        """Synthetic valid focus must win over a stale activity record."""
        fixture = dict(FIXTURES["tivimate"])
        fixture["window"] = "mCurrentFocus=Window{abc u0 com.example.focus/.Player}\n"
        result, calls = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), "com.example.focus")
        self.assertNotIn("dumpsys activity activities", calls)

    def test_null_focus_falls_back(self):
        """Synthetic null focus fields must not be mistaken for an app."""
        fixture = dict(FIXTURES["tivimate"])
        fixture["window"] = "mCurrentFocus=null\nmFocusedApp=null\n"
        result, _ = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), fixture["expected"])

    def test_legacy_system_package_takes_priority(self):
        """Synthetic framework package android must keep its native priority."""
        fixture = dict(FIXTURES["tivimate"])
        fixture["window"] = "mCurrentFocus=Window{abc u0 android/.SystemDialog}\n"
        result, calls = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), "android")
        self.assertNotIn("dumpsys activity activities", calls)

    def test_existing_sony_picture_off_behavior_is_preserved(self):
        """Preserve the Sony Picture Off example already present upstream."""
        fixture = dict(FIXTURES["tivimate"])
        fixture["window"] = (
            "mCurrentFocus=Window{c52eaa8 u0 com.sony.dtv.sonysystemservice}\n"
            "mFocusedApp=AppWindowToken{11da138 token=Token{19ea99b "
            "ActivityRecord{c4d9aa u0 tunein.player/tunein.ui.leanback.ui.activities.TvHomeActivity t2424}}}\n"
        )
        result, calls = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), "tunein.player")
        self.assertNotIn("dumpsys activity activities", calls)

    def test_no_foreground_activity(self):
        """Synthetic absent windows and activities must not invent an app."""
        fixture = {"window": "", "activity": ""}
        result, _ = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertIsNone(self.tv._current_app(result.stdout.strip()))

    def test_activity_stderr_is_not_an_app(self):
        """Synthetic dumpsys diagnostics must not corrupt the package reply."""
        result, _ = self.run_query(self.tv._cmd_current_app(), FIXTURES["tivimate"], activity_stderr="Broken pipe\n")
        self.assertEqual(result.stdout.strip(), "ar.tvplayer.tv")
        self.assertEqual(result.stderr, "")

    def test_secondary_android_user(self):
        """Synthetic Android user IDs must not be limited to u0."""
        fixture = dict(FIXTURES["tivimate"])
        fixture["activity"] = fixture["activity"].replace(" u0 ", " u10 ")
        result, _ = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), fixture["expected"])

    def test_media_session_query_uses_same_app_detection(self):
        """Synthetic media-session states must retain their normal meaning."""
        for state in (2, 3):
            with self.subTest(state=state):
                media = (
                    "Sessions Stack - have 1 sessions:\n"
                    "      package=ar.tvplayer.tv\n"
                    "      state=PlaybackState {state=" + str(state) + ", position=100}\n"
                )
                result, _ = self.run_query(
                    self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media
                )
                self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", state))

    def test_missing_media_session_stays_unknown(self):
        """A corrected app ID must not manufacture playback information."""
        result, _ = self.run_query(
            self.tv._cmd_current_app_media_session_state(),
            FIXTURES["tivimate"],
            media="Sessions Stack - have 0 sessions:\n",
        )
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", None))

    def test_empty_app_skips_media_session_query(self):
        """Live standby must not send an empty pattern to grep."""
        result, calls = self.run_query(self.tv._cmd_current_app_media_session_state(), FIXTURES["standby"])
        self.assertEqual(result.stdout.strip(), "")
        self.assertEqual(result.stderr, "")
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), (None, None))
        self.assertNotIn("dumpsys media_session", calls)

    def test_same_app_is_not_relaunched(self):
        """Already-foreground TiviMate must not receive another launch."""
        _, calls = self.run_query(self.tv._cmd_launch_app("ar.tvplayer.tv"), FIXTURES["tivimate"])
        self.assertFalse(any(call.startswith("monkey ") for call in calls))

    def test_different_app_can_launch(self):
        """The fallback must also work in the shared launch command."""
        _, calls = self.run_query(self.tv._cmd_launch_app("ar.tvplayer.tv"), FIXTURES["home"])
        self.assertIn("monkey -p ar.tvplayer.tv -c android.intent.category.LEANBACK_LAUNCHER --pct-syskeys 0 1", calls)

    def test_app_can_launch_when_focus_is_empty(self):
        """An unknown app must not cause an empty shell comparison error."""
        result, calls = self.run_query(self.tv._cmd_launch_app("ar.tvplayer.tv"), FIXTURES["standby"])
        self.assertEqual(result.stderr, "")
        self.assertTrue(any(call.startswith("monkey -p ar.tvplayer.tv ") for call in calls))

    def test_custom_commands_keep_priority(self):
        """Explicit user overrides must remain effective for Sony too."""
        self.tv.customize_command(constants.CUSTOM_CURRENT_APP, "echo custom.app")
        self.tv.customize_command(constants.CUSTOM_CURRENT_APP_MEDIA_SESSION_STATE, "echo custom.session")
        self.tv.customize_command(constants.CUSTOM_LAUNCH_APP, "echo launch {0}")
        self.assertEqual(self.tv._cmd_current_app(), "echo custom.app")
        self.assertEqual(self.tv._cmd_current_app_media_session_state(), "echo custom.session")
        self.assertEqual(self.tv._cmd_launch_app("ar.tvplayer.tv"), "echo launch ar.tvplayer.tv")

    def test_other_android_devices_keep_native_commands(self):
        """Synthetic device matrix protects all existing command variants."""
        matrix = [
            (
                "Sony",
                "BRAVIA",
                "9",
                constants.CMD_CURRENT_APP,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE,
                constants.CMD_LAUNCH_APP,
            ),
            (
                "Sony",
                "BRAVIA",
                "11",
                constants.CMD_CURRENT_APP11,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE11,
                constants.CMD_LAUNCH_APP11,
            ),
            (
                "Sony",
                "BRAVIA",
                "12",
                constants.CMD_CURRENT_APP12,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE12,
                constants.CMD_LAUNCH_APP12,
            ),
            (
                "Sony",
                "BRAVIA",
                "13",
                constants.CMD_CURRENT_APP13,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE13,
                constants.CMD_LAUNCH_APP13,
            ),
            (
                "Google",
                "Google TV Streamer",
                "14",
                constants.CMD_CURRENT_APP13,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE13,
                constants.CMD_LAUNCH_APP13,
            ),
            (
                "Google",
                "Chromecast",
                "12",
                constants.CMD_CURRENT_APP_GOOGLE_TV,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE_GOOGLE_TV,
                constants.CMD_LAUNCH_APP_GOOGLE_TV,
            ),
            (
                "askey",
                "Streamer",
                "10",
                constants.CMD_CURRENT_APP_ASKEY_STI6130,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE_ASKEY_STI6130,
                constants.CMD_LAUNCH_APP,
            ),
            (
                "Other",
                "TV",
                "10",
                constants.CMD_CURRENT_APP,
                constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE,
                constants.CMD_LAUNCH_APP,
            ),
        ]
        for manufacturer, model, version, current, session, launch in matrix:
            with self.subTest(manufacturer=manufacturer, model=model, version=version):
                self.tv.device_properties = {
                    "manufacturer": manufacturer,
                    "model": model,
                    "sw_version": version,
                    "product_id": "sti6130",
                }
                self.assertEqual(self.tv._cmd_current_app(), current)
                self.assertEqual(self.tv._cmd_current_app_media_session_state(), session)
                self.assertEqual(self.tv._cmd_launch_app("example.app"), launch.format("example.app"))

    def test_fire_tv_keeps_native_commands(self):
        """The Android TV quirk must not affect a Fire TV instance."""
        tv = BaseFireTV("unused-offline-host")
        tv.device_properties = dict(self.tv.device_properties)
        self.assertEqual(tv._cmd_current_app(), constants.CMD_CURRENT_APP)
        self.assertEqual(tv._cmd_current_app_media_session_state(), constants.CMD_CURRENT_APP_MEDIA_SESSION_STATE)
        self.assertEqual(tv._cmd_launch_app("example.app"), constants.CMD_LAUNCH_APP_FIRETV.format("example.app"))

    def test_power_queries_are_unchanged(self):
        """Sony parser corrections must not change the power commands."""
        self.assertEqual(self.tv._cmd_turn_off(), constants.CMD_TURN_OFF_ANDROIDTV)
        self.assertEqual(self.tv._cmd_turn_on(), constants.CMD_TURN_ON_ANDROIDTV)

    def test_focus_window_label_is_not_a_package(self):
        fixture = dict(FIXTURES["tivimate"])
        fixture["window"] = "mCurrentFocus=Window{abc u0 DockedStackDivider}\n"
        result, _ = self.run_query(self.tv._cmd_current_app(), fixture)
        self.assertEqual(result.stdout.strip(), "ar.tvplayer.tv")

    def test_session_for_similarly_named_package_is_ignored(self):
        media = (
            "Sessions Stack - have 1 sessions:\n"
            "    player ar.tvplayer.tv.beta/player (userId=0)\n"
            "      package=ar.tvplayer.tv.beta\n"
            "      state=PlaybackState {state=3, position=100}\n"
            "  Session2Tokens:\n"
        )
        result, _ = self.run_query(self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media)
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", None))

    def test_missing_session_state_does_not_read_next_app(self):
        media = (
            "Sessions Stack - have 2 sessions:\n"
            "    first ar.tvplayer.tv/player (userId=0)\n"
            "      package=ar.tvplayer.tv\n"
            "    second com.example.other/player (userId=0)\n"
            "      package=com.example.other\n"
            "      state=PlaybackState {state=3, position=100}\n"
            "  Session2Tokens:\n"
        )
        result, _ = self.run_query(self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media)
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", None))

    def test_session_search_is_not_limited_to_100_lines(self):
        media = (
            "Sessions Stack - have 2 sessions:\n"
            "      package=com.example.other\n"
            + "      metadata: irrelevant\n" * 110
            + "      package=ar.tvplayer.tv\n"
            "      state=PlaybackState {state=2, position=100}\n"
            "  Session2Tokens:\n"
        )
        result, _ = self.run_query(self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media)
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", 2))

    def test_playback_history_outside_session_stack_is_ignored(self):
        media = (
            "Sessions Stack - have 0 sessions:\n"
            "  Session2Tokens:\n"
            "Audio playback history:\n"
            "      package=ar.tvplayer.tv\n"
            "      state=PlaybackState {state=3, position=100}\n"
        )
        result, _ = self.run_query(self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media)
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", None))

    def test_failed_media_session_dump_ignores_partial_stdout(self):
        media = (
            "Sessions Stack - have 1 sessions:\n"
            "      package=ar.tvplayer.tv\n"
            "      state=PlaybackState {state=3, position=100}\n"
            "  Session2Tokens:\n"
        )
        result, _ = self.run_query(
            self.tv._cmd_current_app_media_session_state(), FIXTURES["tivimate"], media=media, media_rc=1
        )
        self.assertEqual(self.tv._current_app_media_session_state(result.stdout), ("ar.tvplayer.tv", None))


if __name__ == "__main__":
    unittest.main()
