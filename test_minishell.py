#!/usr/bin/env python3
"""
Complete End-to-End Integration Test Suite for MiniShell (All 4 Group Members).
Run with:
    python3 -m unittest -v test_minishell
"""
import io
import os
import shutil
import tempfile
import unittest
from typing import Tuple

from minishell import MiniShell


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


class TestMiniShellIntegrated(unittest.TestCase):
    """End-to-end tests verifying Shell Core (M1), Scheduler (M2), Deadlock (M3), and Grep/Compare (M4)."""

    def setUp(self) -> None:
        self.orig_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        for fname in os.listdir(PROJECT_DIR):
            if fname.endswith(".txt"):
                shutil.copy2(os.path.join(PROJECT_DIR, fname), os.path.join(self.temp_dir.name, fname))
        os.makedirs(os.path.join(self.temp_dir.name, "samples"), exist_ok=True)
        for fname in os.listdir(os.path.join(PROJECT_DIR, "samples")):
            if fname.endswith(".txt"):
                shutil.copy2(
                    os.path.join(PROJECT_DIR, "samples", fname),
                    os.path.join(self.temp_dir.name, "samples", fname),
                )
        os.chdir(self.temp_dir.name)
        self.shell = MiniShell(interactive=False)

    def tearDown(self) -> None:
        os.chdir(self.orig_cwd)
        self.temp_dir.cleanup()

    def run_cmd(self, line: str, stdin_text: str = "") -> Tuple[int, str, str]:
        in_buf = io.StringIO(stdin_text)
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        code = self.shell.execute_line(line, stdin=in_buf, stdout=out_buf, stderr=err_buf)
        return code, out_buf.getvalue(), err_buf.getvalue()

    def test_module1_and_member4_grep_in_shell(self) -> None:
        code, out, err = self.run_cmd("grep -n -i deadlock samples/notes.txt")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out, "3:Deadlock needs four conditions\n")

        code, out, err = self.run_cmd('grep -E --groups "([0-9]+)-([0-9]+)" samples/notes.txt')
        self.assertEqual(code, 0, msg=err)
        self.assertIn("group 1: 555", out)
        self.assertIn("group 2: 1234", out)

    def test_module2_scheduler_in_shell(self) -> None:
        for algo in ("fcfs", "sjn", "priority", "rr", "mlq", "mlfq"):
            code, out, err = self.run_cmd(f"sched {algo} --quantum 4 samples/processes1.txt")
            self.assertEqual(code, 0, msg=f"{algo} failed: {err}")
            self.assertIn("Gantt chart:", out)
            self.assertIn("Average waiting time:", out)

        code, out, err = self.run_cmd("sched sjn --preemptive --trace --at 3 samples/processes1.txt")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("SJN (preemptive, SRTF)", out)
        self.assertIn("PCB snapshot at t=3:", out)
        self.assertIn("State transitions:", out)

    def test_module3_deadlock_in_shell(self) -> None:
        code, out, err = self.run_cmd("deadlock banker samples/system_safe.txt --request 1 1 0 2")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("Decision: GRANTED", out)

        code, out, err = self.run_cmd("deadlock detect samples/system_deadlock.txt")
        self.assertEqual(code, 1)
        self.assertIn("DEADLOCK detected", out)
        self.assertIn("Recovery suggestion (bonus):", out)

    def test_module4_compare_in_shell(self) -> None:
        code, out, err = self.run_cmd("compare --quantum 4 samples/processes1.txt")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("Best average waiting time: Multilevel Queue (quantum=4) (6.50)", out)

        code2, out2, err2 = self.run_cmd("sched compare --quantum 4 samples/processes1.txt")
        self.assertEqual(code2, 0, msg=err2)
        self.assertEqual(out, out2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
