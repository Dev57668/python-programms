import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

class DaemonManager:
    """Manages the lifecycle (start, stop, status) of the CodeVault watcher daemon."""

    def __init__(self, project_dir: Path, lifejacket_dir: Path):
        self.project_dir = project_dir.resolve()
        self.lifejacket_dir = lifejacket_dir.resolve()
        self.pid_file = self.lifejacket_dir / "daemon.json"

    def _read_state(self) -> Optional[Dict]:
        """Read the daemon state from the PID file."""
        if not self.pid_file.exists():
            return None
        try:
            with open(self.pid_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception:
            return None

    def _write_state(self, pid: int) -> None:
        """Write the daemon state to the PID file."""
        self.lifejacket_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "pid": pid,
            "project_dir": str(self.project_dir)
        }
        with open(self.pid_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _clear_state(self) -> None:
        """Remove the PID file."""
        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                pass

    def _is_process_alive(self, pid: int) -> bool:
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True # Process exists but we don't have permission to signal it
        except OSError:
            return False

    def _is_our_process(self, pid: int) -> bool:
        """Verify the PID is actually running our python code."""
        if not self._is_process_alive(pid):
            return False
            
        try:
            if os.name == 'nt':
                output = subprocess.check_output(
                    f'wmic process where processid={pid} get commandline',
                    shell=True, text=True, stderr=subprocess.DEVNULL
                )
                return 'python' in output.lower() and ('main.py' in output.lower() or 'codevault' in output.lower())
            else:
                output = subprocess.check_output(
                    ['ps', '-p', str(pid), '-o', 'command='],
                    text=True, stderr=subprocess.DEVNULL
                )
                return 'python' in output.lower() and ('main.py' in output.lower() or 'codevault' in output.lower())
        except Exception:
            # Fallback if ps/wmic fail (e.g. not installed or restricted)
            return True

    def _is_daemon_running(self) -> Tuple[bool, bool, Optional[int]]:
        """
        Check if the daemon is running.
        Returns (is_running, is_stale, pid)
        """
        state = self._read_state()
        if not state:
            return False, False, None
            
        pid = state.get("pid")
        if not pid:
            return False, True, None
            
        if self._is_our_process(pid):
            return True, False, pid
            
        return False, True, pid

    def start(self) -> None:
        """Start the daemon if it's not already running."""
        is_running, is_stale, pid = self._is_daemon_running()
        
        if is_running:
            print(f"[OK] Daemon is already running (PID: {pid}).")
            return
            
        if is_stale:
            print(f"[Info] Found stale PID file (PID: {pid}). Cleaning up...")
            self._clear_state()
            
        # Ensure project dir exists
        if not self.project_dir.exists():
            print(f"[Error] Project directory does not exist: {self.project_dir}")
            sys.exit(1)
            
        # We need to spawn `python main.py watch <project_dir>` in the background
        
        
        # We use subprocess.Popen to detach the process
        # On Windows, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        # On Unix, preexec_fn=os.setpgrp or start_new_session=True
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0x00000200)
            kwargs['creationflags'] |= getattr(subprocess, 'DETACHED_PROCESS', 0x00000008)
        else:
            kwargs['start_new_session'] = True
            
        # Suppress output in the detached process
        devnull = open(os.devnull, 'w')
        
        try:
            process = subprocess.Popen(
            [sys.executable, "-m", "codevault.cli", "watch", str(self.project_dir)],
                stdin=devnull,
                stdout=devnull,
                stderr=devnull,
                cwd=str(self.project_dir),
                **kwargs
            )
            
            self._write_state(process.pid)
            print(f"[OK] Started CodeVault daemon (PID: {process.pid}) for {self.project_dir}")
        except Exception as e:
            print(f"[Error] Failed to start daemon: {e}")
            sys.exit(1)

    def stop(self) -> None:
        """Stop the daemon gracefully."""
        is_running, is_stale, pid = self._is_daemon_running()
        
        if not is_running and not is_stale:
            print("[OK] Daemon is already stopped.")
            return
            
        if is_stale:
            print(f"[Info] Daemon is not running (stale PID {pid}). Cleaning up state.")
            self._clear_state()
            return
            
        print(f"Requesting graceful shutdown of daemon (PID: {pid})...")
        try:
            # Send SIGTERM
            if os.name == 'nt':
                os.kill(pid, signal.CTRL_BREAK_EVENT)
            else:
                os.kill(pid, signal.SIGTERM)
                
            # Wait gracefully for up to 5 seconds
            for _ in range(25):
                if not self._is_process_alive(pid):
                    break
                time.sleep(0.2)
                
            if self._is_process_alive(pid):
                print(f"[Warning] Daemon {pid} did not exit within 5 seconds. Forcing termination.")
                try:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/PID', str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        os.kill(pid, signal.SIGKILL)
                except Exception:
                    pass
                time.sleep(0.5)
            else:
                print("[OK] Daemon stopped successfully.")
                
            self._clear_state()
        except ProcessLookupError:
            print(f"[Info] Process {pid} already exited. Cleaning up.")
            self._clear_state()
        except PermissionError:
            print(f"[Error] Permission denied to stop process {pid}.")
            sys.exit(1)
        except Exception as e:
            print(f"[Error] Failed to stop daemon: {e}")
            sys.exit(1)

    def status(self) -> dict:
        """Get the daemon status."""
        is_running, is_stale, pid = self._is_daemon_running()
        
        if is_running:
            return {"status": "RUNNING", "pid": pid}
        elif is_stale:
            return {"status": "STALE", "pid": pid}
        else:
            return {"status": "STOPPED", "pid": None}
