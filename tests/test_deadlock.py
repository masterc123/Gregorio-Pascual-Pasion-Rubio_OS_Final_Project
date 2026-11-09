"""Tests for Module 3 (deadlock). Run from the ResourcesLead folder:

    python3 -m unittest discover -s tests -v

Covers: safe state, unsafe state, deadlock detection, recovery, resource requests
(granted / unsafe / must wait / over max), edge cases (single process, no processes)
and bad input. Expected values come from the classic textbook example (Silberschatz).
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import deadlock as dl  # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


def sample_path(name):
    return os.path.join(SAMPLES, name)


def load_system(name):
    with open(sample_path(name), encoding="utf-8") as f:
        return dl.parse_system(f.read())


class SafetyTests(unittest.TestCase):
    def test_safe_state_and_sequence(self):
        s = load_system("system_safe.txt")
        safe, seq, _, _ = dl.safety_check(s.avail, s.alloc, s.need())
        self.assertTrue(safe)
        self.assertEqual(seq, [1, 3, 4, 0, 2])

    def test_unsafe_state(self):
        s = load_system("system_deadlock.txt")
        safe, seq, _, stuck = dl.safety_check(s.avail, s.alloc, s.need())
        self.assertFalse(safe)
        self.assertEqual(stuck, [0, 1, 2])

    def test_single_process_edge_case(self):
        s = load_system("system_single.txt")
        safe, seq, _, _ = dl.safety_check(s.avail, s.alloc, s.need())
        self.assertTrue(safe)
        self.assertEqual(seq, [0])

    def test_no_processes_edge_case(self):
        s = load_system("system_empty.txt")
        safe, seq, _, _ = dl.safety_check(s.avail, s.alloc, s.need())
        self.assertTrue(safe)
        self.assertEqual(seq, [])


class DetectionTests(unittest.TestCase):
    def test_detection_finds_circular_wait(self):
        s = load_system("system_deadlock.txt")
        stuck, order, _ = dl.detect(s.avail, s.alloc, s.request)
        self.assertEqual(stuck, [0, 1, 2])
        self.assertEqual(order, [])      # P3 holds nothing; nobody else can finish

    def test_detection_on_safe_state(self):
        s = load_system("system_safe.txt")
        stuck, order, _ = dl.detect(s.avail, s.alloc, s.need())
        self.assertEqual(stuck, [])
        self.assertEqual(sorted(order), [0, 1, 2, 3, 4])

    def test_no_processes(self):
        s = load_system("system_empty.txt")
        self.assertEqual(dl.detect(s.avail, s.alloc, s.need())[0], [])

    def test_recovery_plan_removes_deadlock(self):
        s = load_system("system_deadlock.txt")
        plan = dl.recovery_plan(s.avail, s.alloc, s.request)
        self.assertTrue(plan)
        alloc = [list(r) for r in s.alloc]
        avail = list(s.avail)
        for victim in plan:
            avail = [a + b for a, b in zip(avail, alloc[victim])]
            alloc[victim] = [0] * s.m
        self.assertEqual(dl.detect(avail, alloc, s.request)[0], [])


class RequestTests(unittest.TestCase):
    def test_request_granted(self):
        # Textbook: P1 asks (1,0,2) -> state stays safe, granted
        s = load_system("system_safe.txt")
        ok, _, new_alloc, new_avail, seq, _ = dl.check_request(s, 1, [1, 0, 2])
        self.assertTrue(ok)
        self.assertEqual(new_alloc[1], [3, 0, 2])
        self.assertEqual(new_avail, [2, 3, 0])
        self.assertEqual(seq, [1, 3, 4, 0, 2])

    def test_request_denied_unsafe_and_must_wait(self):
        # After P1's grant: P0 asking (0,2,0) is unsafe; P4 asking (3,3,0) must wait.
        s = load_system("system_after_p1.txt")
        ok, reason, *_ = dl.check_request(s, 0, [0, 2, 0])
        self.assertFalse(ok)
        self.assertIn("UNSAFE", reason)
        ok, reason, *_ = dl.check_request(s, 4, [3, 3, 0])
        self.assertFalse(ok)
        self.assertIn("must wait", reason)

    def test_request_over_maximum_claim(self):
        s = load_system("system_safe.txt")
        ok, reason, *_ = dl.check_request(s, 0, [8, 0, 0])
        self.assertFalse(ok)
        self.assertIn("maximum", reason)

    def test_negative_request_rejected(self):
        s = load_system("system_safe.txt")
        with self.assertRaises(dl.DeadlockError):
            dl.check_request(s, 0, [-1, 0, 0])


class InputTests(unittest.TestCase):
    def test_bad_input_files(self):
        with open(sample_path("system_bad.txt"), encoding="utf-8") as f:
            with self.assertRaises(dl.DeadlockError):
                dl.parse_system(f.read())
        with self.assertRaises(dl.DeadlockError):       # allocation > max
            dl.parse_system("processes 1\nresources 1\nallocation\n5\n"
                            "available\n0\nmax\n3\n").need()
        with self.assertRaises(dl.DeadlockError):       # 'processes' missing
            dl.parse_system("resources 2\nallocation\n1 1\n")
        with self.assertRaises(dl.DeadlockError):       # unknown keyword
            dl.parse_system("processes 1\nresources 1\nfoo\n")


class CommandLineTests(unittest.TestCase):
    """Run `python3 deadlock.py ...` as a user would and check output and exit status."""

    def run_cli(self, *args):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "deadlock.py"), *args],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        return r.returncode, r.stdout, r.stderr

    def test_safe_exit_zero(self):
        code, out, _ = self.run_cli("banker", sample_path("system_safe.txt"))
        self.assertEqual(code, 0)
        self.assertIn("< P1, P3, P4, P0, P2 >", out)

    def test_deadlock_exit_one(self):
        code, out, _ = self.run_cli("detect", sample_path("system_deadlock.txt"))
        self.assertEqual(code, 1)
        self.assertIn("DEADLOCK detected", out)

    def test_request_denied_exit_one(self):
        code, out, _ = self.run_cli("banker", sample_path("system_after_p1.txt"),
                                    "--request", "0", "0", "2", "0")
        self.assertEqual(code, 1)
        self.assertIn("DENIED", out)

    def test_bad_arguments_exit_two(self):
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("banker", "no_such_file.txt")[0], 2)
        self.assertEqual(self.run_cli("banker", sample_path("system_bad.txt"))[0], 2)
        self.assertEqual(self.run_cli("banker", sample_path("system_safe.txt"),
                                      "--request", "9", "0", "0", "0")[0], 2)


if __name__ == "__main__":
    unittest.main()
