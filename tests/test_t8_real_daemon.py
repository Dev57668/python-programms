import json
import os
import signal
import sys
import time
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from config import Config
from daemon import DaemonManager


def test_daemon_real_subprocess_lifecycle(tmp_path):
    """
    Test real subprocess lifecycle without mocking.
    We will create a dummy script that loops indefinitely and see if DaemonManager 
    can start it, verify it's running, and stop it.
    """
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    lifejacket_dir = project_dir / ".lifejacket"
    
    # We will override the main script the daemon starts
    # Since daemon.py hardcodes Path(__file__).parent / "main.py",
    # we will patch JUST the script path in DaemonManager.
    dummy_script = tmp_path / "main.py"
    dummy_script.write_text(
        "import time, sys, signal\n"
        "def handler(s, f): sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, handler)\n"
        "def main():\n"
        "    while True: time.sleep(1)\n"
        "if __name__ == '__main__': main()\n"
    )

    dm = DaemonManager(project_dir, lifejacket_dir)
    
    # Verify not running initially
    is_running, is_stale, pid = dm._is_daemon_running()
    assert not is_running
    assert not is_stale
    
    # Start it using a mocked main script path so it just sleeps
    with patch("daemon.Path") as mock_path:
        # Mock Path(__file__).parent / "main.py" to point to our dummy script
        class FakePath:
            def __init__(self, *args, **kwargs):
                pass
            @property
            def parent(self):
                class Parent:
                    def __truediv__(self, other):
                        return dummy_script
                return Parent()
                
        mock_path.side_effect = FakePath
        
        # We need to temporarily disable _is_our_process check because our 
        # dummy script might not have "python" and "main.py" strictly in 
        # check_output if the path is weird, but actually it should have.
        # However, to be safe and avoid ps/wmic flakiness in tests, we'll patch it.
        with patch.object(DaemonManager, '_is_our_process', return_value=True):
            dm.start()
            
            # Now wait a tiny bit and check status
            time.sleep(0.5)
            
            is_running, is_stale, pid = dm._is_daemon_running()
            assert is_running is True
            assert pid is not None
            
            # The process should actually be alive
            assert dm._is_process_alive(pid) is True
            
            # Stop it
            dm.stop()
            
            # The test runner is the parent, so the child becomes a zombie.
            # We must reap it so os.kill(pid, 0) returns False.
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
                
            # Ensure it is dead
            time.sleep(0.5)
            assert dm._is_process_alive(pid) is False
            
            # State file should be gone
            assert not dm.pid_file.exists()
