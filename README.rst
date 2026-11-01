python-androidtv
================

A development fork of `JeffLIrion/python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_ for playback detection and ADB reliability fixes.

Current changes
---------------

The current changes address playback reporting on Sony TVs running Android 10:

* Recover the foreground app when window-focus fields are missing.
* Read that app's current media audio players instead of historical events.
* Match media sessions to the exact app and ignore incomplete or failed replies.

The detection is shared across apps. Existing custom commands and state-detection rules keep their priority. Other device families retain their existing behavior.

The code changes are kept on the `sony-android10-playback branch <https://github.com/simonmainguy/python-androidtv/tree/sony-android10-playback>`_ separately from this fork's documentation.

Testing
-------

Device testing used a Sony XBR-65A8H running Android 10 with TiviMate, YouTube and Angel. Play, pause, resume, muted playback, menus and standby were checked. Netflix and Prime Video have not been tested.

The test suite includes recorded replies from the TV and synthetic edge cases. Run it with:

.. code-block:: console

   python -m pytest -q tests

A standalone runner for the Sony parser tests is also available:

.. code-block:: console

   python scripts/run_sony_offline_tests.py

Audio-player data does not reliably distinguish buffering from a deliberate pause.

Home Assistant
--------------

The changes have been tested against the TV, but validation inside Home Assistant is still pending. Custom integration packaging is being developed in `ha-androidtv-adb <https://github.com/simonmainguy/ha-androidtv-adb>`_.

There is no published release of this fork yet. Installing ``androidtv`` from PyPI installs the upstream package.

Credits
-------

The original library and documentation are at `JeffLIrion/python-androidtv <https://github.com/JeffLIrion/python-androidtv>`_ and `androidtv.readthedocs.io <https://androidtv.readthedocs.io>`_.

This project builds on work by Jeff Irion and the upstream contributors, including `python-firetv <https://github.com/happyleavesaoc/python-firetv>`_ by happyleavesaoc and the Android TV component by a1ex4. It uses `adb-shell <https://github.com/JeffLIrion/adb_shell>`_ and `pure-python-adb <https://github.com/Swind/pure-python-adb>`_.

The upstream MIT license is retained in LICENSE.
