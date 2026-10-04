"""Windows-only checks for the desktop process paths. Other platforms skip."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    # os.kill(pid, 0) is unreliable on Windows; ask tasklist instead.
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = (result.stdout or "") + (result.stderr or "")
    if "No tasks" in text or "没有运行" in text:
        return False
    return str(pid) in text


@unittest.skipUnless(sys.platform == "win32", "Windows only")
class WindowsDesktopTests(unittest.TestCase):
    def test_venv_python_path(self):
        env = os.environ.copy()
        env.pop("ZINTRIQ_PYTHON", None)
        script = textwrap.dedent(
            """
            const path = require("path");
            const { resolvePythonExecutable } = require("./flask_host");
            const got = resolvePythonExecutable();
            const expected = path.join(path.resolve(__dirname, ".."), ".venv", "Scripts", "python.exe");
            if (got !== expected) {
              console.error("python path mismatch");
              process.exit(1);
            }
            """
        )
        proc = subprocess.run(
            ["node", "-e", script],
            cwd=DESKTOP,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("ZINTRIQ_DESKTOP_TOKEN", proc.stdout + proc.stderr)

    def test_taskkill_stops_python_sleeper(self):
        parent_script = textwrap.dedent(
            """
            const { spawn } = require("child_process");
            const python = process.env.WIN_TEST_PYTHON;
            const child = spawn(python, ["-c", "import time; time.sleep(60)"], {
              stdio: "ignore",
              windowsHide: true,
            });
            child.on("error", () => process.exit(2));
            process.stdout.write(String(child.pid) + "\\n");
            setInterval(() => {}, 1000);
            """
        )
        env = os.environ.copy()
        env["WIN_TEST_PYTHON"] = sys.executable
        parent = subprocess.Popen(
            ["node", "-e", parent_script],
            cwd=DESKTOP,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        child_pid = 0
        try:
            line = parent.stdout.readline()
            child_pid = int(line.strip())
            kill_script = textwrap.dedent(
                """
                const { forceKill } = require("./flask_host");
                forceKill({ pid: Number(process.argv[1]), exitCode: null });
                """
            )
            killer = subprocess.run(
                ["node", "-e", kill_script, str(parent.pid)],
                cwd=DESKTOP,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(killer.returncode, 0, killer.stdout + killer.stderr)
            deadline = time.time() + 15
            while time.time() < deadline and (_alive(parent.pid) or _alive(child_pid)):
                time.sleep(0.25)
            self.assertFalse(_alive(parent.pid), f"parent {parent.pid} still alive")
            self.assertFalse(_alive(child_pid), f"child {child_pid} still alive")
        finally:
            if parent.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(parent.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            if parent.stdout:
                parent.stdout.close()
            if parent.stderr:
                parent.stderr.close()

    def test_msvcrt_lock_leaves_pid_readable(self):
        data_dir = Path(tempfile.mkdtemp(prefix="zintriq-msvcrt-"))
        holder_code = textwrap.dedent(
            """
            import os
            import sys
            import time
            from pathlib import Path

            sys.path.insert(0, os.environ["REPO_ROOT"])
            from desktop.server_mode import _try_lock, _write_private

            data = Path(os.environ["ZINTRIQ_DATA_DIR"])
            data.mkdir(parents=True, exist_ok=True)
            fd = os.open(data / "zintriq.lock", os.O_CREAT | os.O_RDWR, 0o600)
            if os.fstat(fd).st_size < 1:
                os.write(fd, b"\\0")
            _try_lock(fd)
            _write_private(data / "zintriq.pid", "pid=%s\\nport=9\\n" % os.getpid())
            sys.stdout.write("HELD %s\\n" % os.getpid())
            sys.stdout.flush()
            time.sleep(30)
            """
        )
        env = os.environ.copy()
        env["REPO_ROOT"] = str(ROOT)
        env["ZINTRIQ_DATA_DIR"] = str(data_dir)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        holder = subprocess.Popen(
            [sys.executable, "-c", holder_code],
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            line = holder.stdout.readline()
            self.assertTrue(line.startswith("HELD "), holder.stderr.read() if holder.poll() else line)
            held_pid = int(line.split()[1])
            pid_text = (data_dir / "zintriq.pid").read_text(encoding="utf-8")
            self.assertIn(f"pid={held_pid}", pid_text)
            challenger_code = textwrap.dedent(
                """
                import os
                import sys
                from pathlib import Path

                sys.path.insert(0, os.environ["REPO_ROOT"])
                from desktop.server_mode import _try_lock

                data = Path(os.environ["ZINTRIQ_DATA_DIR"])
                text = (data / "zintriq.pid").read_text(encoding="utf-8")
                if "pid=" not in text:
                    raise SystemExit("pid file unreadable")
                fd = os.open(data / "zintriq.lock", os.O_RDWR)
                try:
                    _try_lock(fd)
                except OSError:
                    sys.stdout.write("LOCKED\\n")
                else:
                    raise SystemExit("lock should fail")
                """
            )
            challenger = subprocess.run(
                [sys.executable, "-c", challenger_code],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(challenger.returncode, 0, challenger.stdout + challenger.stderr)
            self.assertIn("LOCKED", challenger.stdout)
            self.assertIn(str(held_pid), (data_dir / "zintriq.pid").read_text(encoding="utf-8"))
        finally:
            if holder.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(holder.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            if holder.stdout:
                holder.stdout.close()
            if holder.stderr:
                holder.stderr.close()
            import shutil

            shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
