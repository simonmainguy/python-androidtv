python-androidtv
================

A development fork of `JeffLIrion/python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_ for playback detection and ADB reliability fixes.

Current changes
---------------

The current changes improve Sony Android 10 playback reporting and support named Android media-session states:

* Recover the foreground app when window-focus fields are missing.
* Read that app's current media audio players instead of historical events.
* Match media sessions to the exact app and ignore incomplete or failed replies.
* Parse both numeric states and named states such as ``PLAYING(3)`` and ``PAUSED(2)``.

The detection is shared across apps. Existing custom commands and state-detection rules keep their priority. Sony foreground/audio workarounds remain device-specific, while the shared session parser accepts both numeric and named formats.

The code changes are kept on the `playback-detection branch <https://github.com/simonmainguy/python-androidtv/tree/playback-detection>`_ separately from this fork's documentation.

Testing
-------

Device testing used a Sony XBR-65A8H running Android 10 with TiviMate, YouTube and Angel. Play, pause, resume, muted playback, menus and standby were checked. Netflix and Prime Video have not been tested.

The test suite includes recorded replies from the TV and synthetic edge cases. Run it with:

.. code-block:: console

   python -m pytest -q tests

A standalone runner for the Sony parser tests is also available:

.. code-block:: console

   python scripts/run_sony_offline_tests.py

Google TV Streamer Android 14 captures also cover YouTube play, pause, resume and menus. Parser tests cover both numeric and named states, multi-digit codes and malformed replies. Home Assistant replay and live tests are recorded in the integration repository linked below.

Audio-player data does not reliably distinguish buffering from a deliberate pause.

Home Assistant
--------------

A custom integration and a pinned Linux development environment are available in `ha-androidtv-adb <https://github.com/simonmainguy/ha-androidtv-adb>`_. Automated integration tests replay the recorded replies through Home Assistant 2026.10.4 entities and check configuration, reloads and disconnect recovery. A separate live Home Assistant trial checked all three Sony apps, volume, standby/wake, entry reloads and a full restart. Google TV Streamer checks initially exposed a named-state parsing limitation shared with the original library. The follow-up parser fix is included in custom integration 0.1.0b2. See the integration repository's `test results <https://github.com/simonmainguy/ha-androidtv-adb/blob/main/docs/testing.md>`_ for the verified scope and remaining limits.

There is no published release of this fork yet. Installing ``androidtv`` from PyPI installs the upstream package.

Credits
-------

The original library and documentation are at `JeffLIrion/python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_ and `androidtv.readthedocs.io <https://androidtv.readthedocs.io>`_.

This project builds on work by Jeff Irion and the upstream contributors, including `python-firetv <https://github.com/happyleavesaoc/python-firetv>`_ by happyleavesaoc and the Android TV component by a1ex4. It uses `adb-shell <https://github.com/JeffLIrion/adb_shell>`_ and `pure-python-adb <https://github.com/Swind/pure-python-adb>`_.

The upstream MIT license is retained in LICENSE.
