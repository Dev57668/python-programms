import json
import os
import signal
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from config import Config
from daemon import DaemonManager

@pytest.fixture
def temp_config_file(tmp_path):
    config_file = tmp_path / "config.json"
    data = {
        "max_snapshots": 10,
        "max_age_days": 5
    }
    config_file.write_text(json.dumps(data))
    return config_file

@pytest.fixture
def test_config(temp_config_file):
    return Config(temp_config_file)

def test_config_show(test_config, capsys):
    test_config.show()
    captured = capsys.readouterr()
    assert "Effective Configuration" in captured.out
    assert "10 (Custom)" in captured.out
    assert "5 (Custom)" in captured.out

def test_config_set_valid(test_config):
    assert test_config.set_key("max_snapshots", "50") is True
    assert test_config.max_snapshots == 50
    # verify save
    data = json.loads(test_config.config_path.read_text())
    assert data["max_snapshots"] == 50

def test_config_set_invalid(test_config):
    assert test_config.set_key("max_snapshots", "abc") is False
    assert test_config.set_key("max_snapshots", "-1") is False
    assert test_config.set_key("log_level", "FOO") is False
    assert test_config.set_key("invalid_key", "value") is False

def test_config_set_list_parsing(test_config):
    assert test_config.set_key("ignore_patterns", "**/node_modules,build/**,*.tmp") is True
    assert "**/node_modules" in test_config.ignored_directories
    assert "build/**" in test_config.ignored_directories
    assert "*.tmp" in test_config.ignored_directories

@pytest.fixture
def daemon_env(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    lifejacket_dir = project_dir / ".lifejacket"
    lifejacket_dir.mkdir()
    dm = DaemonManager(project_dir, lifejacket_dir)
    return dm

def test_daemon_status_stopped(daemon_env):
    status = daemon_env.status()
    assert status["status"] == "STOPPED"
    assert status["pid"] is None

@patch("daemon.os.kill")
def test_daemon_status_running(mock_kill, daemon_env):
    daemon_env._write_state(12345)
    # mock_kill won't raise ProcessLookupError, meaning process is alive
    status = daemon_env.status()
    assert status["status"] == "RUNNING"
    assert status["pid"] == 12345
    mock_kill.assert_called_with(12345, 0)

@patch("daemon.os.kill")
def test_daemon_status_stale(mock_kill, daemon_env):
    daemon_env._write_state(12345)
    mock_kill.side_effect = ProcessLookupError()
    status = daemon_env.status()
    assert status["status"] == "STALE"
    assert status["pid"] == 12345

@patch("daemon.subprocess.Popen")
@patch("daemon.DaemonManager._is_daemon_running")
def test_daemon_start(mock_is_running, mock_popen, daemon_env):
    mock_is_running.return_value = (False, False, None)
    
    mock_proc = MagicMock()
    mock_proc.pid = 9999
    mock_popen.return_value = mock_proc
    
    daemon_env.start()
    
    mock_popen.assert_called_once()
    assert daemon_env.pid_file.exists()
    state = daemon_env._read_state()
    assert state["pid"] == 9999
    assert state["project_dir"] == str(daemon_env.project_dir)

@patch("daemon.DaemonManager._is_daemon_running")
def test_daemon_start_already_running(mock_is_running, daemon_env, capsys):
    mock_is_running.return_value = (True, False, 1234)
    daemon_env.start()
    captured = capsys.readouterr()
    assert "already running" in captured.out

@patch("daemon.os.kill")
@patch("daemon.DaemonManager._is_daemon_running")
def test_daemon_stop_graceful(mock_is_running, mock_kill, daemon_env):
    mock_is_running.return_value = (True, False, 1234)
    daemon_env._write_state(1234)
    daemon_env.stop()
    
    if os.name == 'nt':
        mock_kill.assert_any_call(1234, signal.CTRL_BREAK_EVENT)
    else:
        mock_kill.assert_any_call(1234, signal.SIGTERM)
        
    assert not daemon_env.pid_file.exists()

@patch("daemon.DaemonManager._is_daemon_running")
def test_daemon_stop_stale(mock_is_running, daemon_env, capsys):
    mock_is_running.return_value = (False, True, 1234)
    daemon_env._write_state(1234)
    daemon_env.stop()
    captured = capsys.readouterr()
    assert "not running" in captured.out
    assert not daemon_env.pid_file.exists()
