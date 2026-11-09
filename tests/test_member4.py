"""Tests for Member 4's parts: the grep-like command and the Module 4 comparison.

Run from the Member4 folder:   python3 -m unittest discover -s tests -v
"""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import scheduler as sc                   # noqa: E402
from grep_cmd import cmd_grep            # noqa: E402
from report import cmd_compare           # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
NOTES = os.path.join(SAMPLES, "notes.txt")


def sample(name):
    return os.path.join(SAMPLES, name)


class FakeCtx:
    """Collects what a command prints, like the shell's context does."""

    def __init__(self, stdin=None):
        self.stdin, self.out, self.err = stdin, [], []

    def println(self, text=""):
        self.out.append(text + "\n")

    def error(self, text):
        self.err.append(text + "\n")

    def read_stdin(self):
        return self.stdin or ""

    @property
    def text(self):
        return "".join(self.out)


def grep(*args, stdin=None):
    ctx = FakeCtx(stdin)
    status = cmd_grep(list(args), ctx)
    return ctx.text, "".join(ctx.err), status


def compare(*args, stdin=None):
    ctx = FakeCtx(stdin)
    status = cmd_compare(list(args), ctx)
    return ctx.text, "".join(ctx.err), status


# ======================================================== grep-like search
class GrepTests(unittest.TestCase):
    def test_plain_text_match(self):
        out, _, st = grep("Deadlock", NOTES)
        self.assertEqual((out, st), ("Deadlock needs four conditions\n", 0))

    def test_no_match_gives_status_1(self):
        self.assertEqual(grep("zebra", NOTES), ("", "", 1))

    def test_plain_mode_treats_dot_literally(self):
        self.assertEqual(grep("Dead.ock", NOTES)[2], 1)

    def test_options(self):
        self.assertEqual(grep("-c", "error", NOTES)[0], "1\n")
        self.assertEqual(grep("-ci", "error", NOTES)[0], "2\n")
        self.assertTrue(grep("-n", "Gantt", NOTES)[0].startswith("2:"))
        self.assertEqual(grep("-vc", "e", NOTES)[0], "0\n")

    def test_regex_bonus(self):
        self.assertIn("Deadlock", grep("-E", "Dead.ock", NOTES)[0])
        self.assertEqual(grep("-oE", "[0-9]+-[0-9]+", NOTES)[0], "555-1234\n555-9876\n")
        out = grep("-E", "--groups", "([0-9]+)-([0-9]+)", NOTES)[0]
        self.assertIn("group 1: 555", out)
        self.assertIn("group 2: 1234", out)

    def test_escaping_with_backslash(self):
        self.assertEqual(grep("-E", r"conditions\b", NOTES)[2], 0)
        self.assertEqual(grep("-E", r"\.", NOTES)[2], 1)       # no literal dot in the file

    def test_reads_standard_input(self):
        self.assertEqual(grep("alp", stdin="alpha\nbeta\n")[0], "alpha\n")

    def test_errors(self):
        _, err, st = grep("x", "no_such_file.txt")
        self.assertEqual(st, 2)
        self.assertIn("No such file", err)
        _, err, st = grep("-E", "(", NOTES)
        self.assertEqual(st, 2)
        self.assertIn("invalid regular expression", err)
        self.assertEqual(grep()[2], 2)                          # no pattern
        self.assertEqual(grep("-z", "x", NOTES)[2], 2)          # unknown option


# =================================================== Module 4: comparison
class CompareTests(unittest.TestCase):
    def test_numbers_quoted_in_the_report(self):
        """The tables in the written report must match the code (waiting, turnaround)."""
        expected = {
            "processes1.txt": {"fcfs": (8.75, 15.25), "sjn": (7.75, 14.25), "priority": (7.75, 14.25),
                               "rr": (11.75, 18.25), "mlq": (6.50, 13.00), "mlfq": (11.75, 18.25)},
            "processes2.txt": {"fcfs": (8.83, 13.83), "sjn": (6.67, 11.67), "priority": (8.83, 13.83),
                               "rr": (11.67, 16.67), "mlq": (9.17, 14.17), "mlfq": (12.00, 17.00)},
            "processes3.txt": {"fcfs": (8.62, 13.12), "sjn": (8.25, 12.75), "priority": (9.62, 14.12),
                               "rr": (8.38, 12.88), "mlq": (8.12, 12.62), "mlfq": (8.00, 12.50)},
        }
        for name, table in expected.items():
            with open(sample(name), encoding="utf-8") as f:
                procs = sc.parse_processes(f.read())
            for algo, (w, t) in table.items():
                r = sc.simulate(algo, procs, quantum=4)
                self.assertAlmostEqual(r.avg_waiting(), w, places=1, msg=(name, algo))
                self.assertAlmostEqual(r.avg_turnaround(), t, places=1, msg=(name, algo))

    def test_output_has_all_six_algorithms_and_a_winner(self):
        out, _, st = compare("--quantum", "4", sample("processes1.txt"))
        self.assertEqual(st, 0)
        for name in ("FCFS", "SJN", "Priority", "Round-Robin", "Multilevel Queue",
                     "Multilevel Feedback Queue"):
            self.assertIn(name, out)
        self.assertIn("Best average waiting time: Multilevel Queue (quantum=4) (6.50)", out)
        self.assertIn("#", out)                                  # the text bar chart

    def test_different_workloads_can_have_different_winners(self):
        w2 = compare("--quantum", "4", sample("processes2.txt"))[0]
        w3 = compare("--quantum", "4", sample("processes3.txt"))[0]
        self.assertIn("Best average waiting time: SJN (6.67)", w2)
        self.assertIn("Best average waiting time: Multilevel Feedback Queue (quantum=4) (8.00)", w3)

    def test_quantum_changes_round_robin(self):
        q2 = compare("--quantum", "2", sample("processes3.txt"))[0]
        self.assertIn("Round-Robin (quantum=2)", q2)
        self.assertIn("7.88", q2)

    def test_edge_cases(self):
        out, _, st = compare(sample("processes_empty.txt"))      # empty queue
        self.assertEqual((st, "No processes to compare." in out), (0, True))
        out, _, st = compare(sample("processes_single.txt"))     # one process: everything ties
        self.assertEqual(st, 0)
        self.assertIn("all algorithms tie", out)
        with open(sample("processes1.txt"), encoding="utf-8") as f:
            out, _, st = compare(stdin=f.read())                 # input from a pipe
        self.assertEqual(st, 0)

    def test_errors(self):
        self.assertEqual(compare("no_such_file.txt")[2], 1)
        self.assertEqual(compare(sample("processes_bad.txt"))[2], 1)
        self.assertEqual(compare("--quantum", "0", sample("processes1.txt"))[2], 1)
        self.assertEqual(compare("--bogus", sample("processes1.txt"))[2], 1)


# ======================================= run as real command-line programs
class CommandLineTests(unittest.TestCase):
    def run_cli(self, script, *args, stdin=None):
        r = subprocess.run([sys.executable, os.path.join(ROOT, script), *args], capture_output=True,
                           text=True, input=stdin, stdin=None if stdin is not None else subprocess.DEVNULL,
                           timeout=30)
        return r.returncode, r.stdout, r.stderr

    def test_grep_command_line(self):
        code, out, _ = self.run_cli("grep_cmd.py", "-n", "-i", "deadlock", NOTES)
        self.assertEqual((code, out), (0, "3:Deadlock needs four conditions\n"))
        self.assertEqual(self.run_cli("grep_cmd.py", "zebra", NOTES)[0], 1)
        self.assertEqual(self.run_cli("grep_cmd.py")[0], 2)
        code, out, _ = self.run_cli("grep_cmd.py", "ap", stdin="apple\nkiwi\napricot\n")   # piped input
        self.assertEqual((code, out), (0, "apple\napricot\n"))

    def test_compare_command_line(self):
        code, out, _ = self.run_cli("report.py", "--quantum", "4", sample("processes1.txt"))
        self.assertEqual(code, 0)
        self.assertIn("Average waiting", out)
        self.assertEqual(self.run_cli("report.py", "no_such_file.txt")[0], 1)


if __name__ == "__main__":
    unittest.main()
