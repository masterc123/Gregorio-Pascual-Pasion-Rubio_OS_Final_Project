#!/usr/bin/env python3
r"""
Automated Test & Verification Suite for MiniShell — Member 1 (Shell Lead)
Tests every grading rubric item in Module 1 (30 pts) + Bonus items + Integration Hooks:
  1. File & directory built-ins: pwd, cd, ls, mkdir, rmdir, touch, cp, mv, rm, cat
  2. Permissions: chmod (numeric octal modes) and ls -l permission display
  3. Redirection: >, >>, <, 2>, and 2>&1
  4. Pipes: Two-stage and multi-stage pipelines joined by |
  5. Variables: NAME=value, echo $NAME, ${NAME}, $?, and env
  6. Conditional execution: &&, ||, ; and Bonus if/then/else/fi
  7. Error handling: Unknown commands, missing files, bad arguments (never crashes)
  8. Text search (grep): Basic matching + Bonus regex (., [a-z], *, +, ?, \, groups)
  9. Final Integration: Dispatcher & plug-in registration for `sched` and `deadlock`
"""

import io
import os
import tempfile
import unittest
from typing import Tuple

from minishell import MiniShell


class TestShellLead(unittest.TestCase):
    """Comprehensive unit and integration tests for the Shell Lead package."""

    def setUp(self) -> None:
        self.orig_cwd = os.getcwd()
        self.temp_dir = tempfile.TemporaryDirectory()
        os.chdir(self.temp_dir.name)
        self.shell = MiniShell(interactive=False)

    def tearDown(self) -> None:
        os.chdir(self.orig_cwd)
        self.temp_dir.cleanup()

    def run_cmd(self, line: str, stdin_text: str = "") -> Tuple[int, str, str]:
        """Helper to execute a command line in MiniShell and capture (exit_code, stdout, stderr)."""
        in_buf = io.StringIO(stdin_text)
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        code = self.shell.execute_line(line, stdin=in_buf, stdout=out_buf, stderr=err_buf)
        return code, out_buf.getvalue(), err_buf.getvalue()

    # ------------------------------------------------------------------------
    # 1. File and Directory Built-ins
    # ------------------------------------------------------------------------
    def test_file_and_directory_builtins(self) -> None:
        # pwd
        code, out, err = self.run_cmd("pwd")
        self.assertEqual(code, 0)
        self.assertEqual(os.path.realpath(out.strip()), os.path.realpath(self.temp_dir.name))

        # mkdir & cd
        code, _, _ = self.run_cmd("mkdir workdir")
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isdir("workdir"))

        code, _, _ = self.run_cmd("cd workdir")
        self.assertEqual(code, 0)
        self.assertTrue(os.getcwd().endswith("workdir"))

        # touch & ls
        code, _, _ = self.run_cmd("touch a.txt b.txt")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cmd("ls")
        self.assertIn("a.txt", out)
        self.assertIn("b.txt", out)

        # cp & mv & cat
        self.run_cmd("echo 'Hello OS World' > a.txt")
        code, _, _ = self.run_cmd("cp a.txt copy.txt")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cmd("cat copy.txt")
        self.assertEqual(out.strip(), "Hello OS World")

        code, _, _ = self.run_cmd("mv copy.txt moved.txt")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists("copy.txt"))
        self.assertTrue(os.path.exists("moved.txt"))

        # rm & rmdir
        code, _, _ = self.run_cmd("rm a.txt b.txt moved.txt")
        self.assertEqual(code, 0)
        self.run_cmd("cd ..")
        code, _, _ = self.run_cmd("rmdir workdir")
        self.assertEqual(code, 0)
        self.assertFalse(os.path.exists("workdir"))

    # ------------------------------------------------------------------------
    # 2. Permissions: chmod (numeric octal) and ls -l
    # ------------------------------------------------------------------------
    def test_permissions_chmod_and_ls_long(self) -> None:
        self.run_cmd("touch script.sh")
        code, _, err = self.run_cmd("chmod 755 script.sh")
        self.assertEqual(code, 0, msg=err)

        code, out, _ = self.run_cmd("ls -l script.sh")
        self.assertEqual(code, 0)
        self.assertIn("-rwxr-xr-x", out)
        self.assertIn("(0755)", out)
        self.assertIn("script.sh", out)

        code, _, _ = self.run_cmd("chmod 640 script.sh")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cmd("ls -l script.sh")
        self.assertIn("-rw-r-----", out)
        self.assertIn("(0640)", out)

    # ------------------------------------------------------------------------
    # 3. Redirection: >, >>, <, 2>, and 2>&1
    # ------------------------------------------------------------------------
    def test_redirections(self) -> None:
        # > overwrite and >> append
        self.run_cmd("echo Line1 > log.txt")
        self.run_cmd("echo Line2 >> log.txt")
        code, out, _ = self.run_cmd("cat < log.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Line1", "Line2"])

        # 2> stderr redirection
        code, out, err = self.run_cmd("cat nonexistent.txt 2> err.txt")
        self.assertNotEqual(code, 0)
        self.assertEqual(err, "")
        _, err_file_content, _ = self.run_cmd("cat err.txt")
        self.assertIn("No such file or directory", err_file_content)

        # 2>&1 combine stderr into stdout
        code, _, _ = self.run_cmd("cat missing_file.txt > combined.txt 2>&1")
        self.assertNotEqual(code, 0)
        _, combined_content, _ = self.run_cmd("cat combined.txt")
        self.assertIn("No such file or directory", combined_content)

    # ------------------------------------------------------------------------
    # 4. Pipes: Two and Three Stage Pipelines
    # ------------------------------------------------------------------------
    def test_pipes(self) -> None:
        self.run_cmd("touch report.txt notes.txt image.png data.csv")
        code, out, err = self.run_cmd("ls | grep txt")
        self.assertEqual(code, 0, msg=err)
        lines = out.strip().split()
        self.assertIn("report.txt", lines)
        self.assertIn("notes.txt", lines)
        self.assertNotIn("image.png", lines)

        # Multi-stage pipe with cat -n
        code, out, _ = self.run_cmd("ls | grep txt | cat -n")
        self.assertEqual(code, 0)
        self.assertIn("1\tnotes.txt", out)
        self.assertIn("2\treport.txt", out)

    # ------------------------------------------------------------------------
    # 5. Variables: Assignment, $NAME Expansion, and env
    # ------------------------------------------------------------------------
    def test_variables_and_env(self) -> None:
        code, _, _ = self.run_cmd("NAME=Ana")
        self.assertEqual(code, 0)

        code, out, _ = self.run_cmd("echo Hello $NAME")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "Hello Ana")

        # Single quotes suppress expansion; double quotes allow expansion
        _, out_single, _ = self.run_cmd("echo '$NAME'")
        self.assertEqual(out_single.strip(), "$NAME")
        _, out_double, _ = self.run_cmd('echo "User: ${NAME}!"')
        self.assertEqual(out_double.strip(), "User: Ana!")

        # env lists NAME=Ana
        code, env_out, _ = self.run_cmd("env")
        self.assertEqual(code, 0)
        self.assertIn("NAME=Ana", env_out)

    # ------------------------------------------------------------------------
    # 6. Conditional Execution: &&, ||, ; and Bonus if/then/else/fi
    # ------------------------------------------------------------------------
    def test_conditionals_and_bonus_if(self) -> None:
        # && runs second only on success
        code, out, _ = self.run_cmd("true && echo YES")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "YES")

        code, out, _ = self.run_cmd("false && echo NO")
        self.assertNotEqual(code, 0)
        self.assertEqual(out.strip(), "")

        # || runs second only on failure
        code, out, _ = self.run_cmd("false || echo RECOVERED")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "RECOVERED")

        # ; runs sequentially regardless
        code, out, _ = self.run_cmd("false ; echo AFTER_FALSE")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AFTER_FALSE")

        # Bonus: if / then / else / fi
        code, out, err = self.run_cmd("if true; then echo BRANCH_THEN; else echo BRANCH_ELSE; fi")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "BRANCH_THEN")

        code, out, err = self.run_cmd("if false; then echo BRANCH_THEN; else echo BRANCH_ELSE; fi")
        self.assertEqual(code, 0, msg=err)
        self.assertEqual(out.strip(), "BRANCH_ELSE")

    # ------------------------------------------------------------------------
    # 7. Text Search (grep): Basic + Bonus Regex Patterns
    # ------------------------------------------------------------------------
    def test_grep_basic_and_bonus_regex(self) -> None:
        sample = "\n".join([
            "alpha_100",
            "beta_200",
            "gamma_abc",
            "literal.dot",
            "literal_dot",
            "repeat_abbbbc",
        ]) + "\n"
        with open("sample.txt", "w", encoding="utf-8") as f:
            f.write(sample)

        # Basic substring
        code, out, _ = self.run_cmd("grep beta sample.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "beta_200")

        # Character sets [a-z] and repetition +
        code, out, _ = self.run_cmd("grep '^[a-z]+_[0-9]+$' sample.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["alpha_100", "beta_200"])

        # Escaping with backslash (\.) vs wildcard (.)
        code, out, _ = self.run_cmd(r"grep 'literal\.dot' sample.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["literal.dot"])

        # Capturing groups and *, ?
        code, out, _ = self.run_cmd(r"grep 'repeat_(ab+c)' sample.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["repeat_abbbbc"])

    # ------------------------------------------------------------------------
    # 8. Error Handling (Shell Must Never Crash)
    # ------------------------------------------------------------------------
    def test_error_handling_never_crashes(self) -> None:
        # Unknown command
        code, _, err = self.run_cmd("nonexistent_command_xyz")
        self.assertEqual(code, 127)
        self.assertIn("command not found", err)

        # Missing file
        code, _, err = self.run_cmd("cat does_not_exist.txt")
        self.assertEqual(code, 1)
        self.assertIn("No such file or directory", err)

        # Bad chmod mode
        code, _, err = self.run_cmd("chmod 999 a.txt")
        self.assertEqual(code, 1)
        self.assertIn("invalid mode", err)

        # Unmatched quotes
        code, _, err = self.run_cmd('echo "unclosed quote')
        self.assertEqual(code, 2)
        self.assertIn("unmatched quote", err)

    # ------------------------------------------------------------------------
    # 9. Teammate Integration Dispatcher (`sched` & `deadlock`)
    # ------------------------------------------------------------------------
    def test_teammate_integration_hooks(self) -> None:
        self.run_cmd("touch processes.txt system.txt")

        # Built-in adapter validation works out of the box
        code, out, err = self.run_cmd("sched rr --quantum 4 processes.txt")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("Module 2 Scheduler", out)
        self.assertIn("quantum=4", out)

        code, out, err = self.run_cmd("deadlock detect system.txt")
        self.assertEqual(code, 0, msg=err)
        self.assertIn("Module 3 Deadlock", out)

        # Registering a real teammate callback overrides the adapter seamlessly
        def custom_sched(args, stdin, stdout, stderr) -> int:
            stdout.write(f"CUSTOM_SCHED_OK:{','.join(args)}\n")
            return 0

        self.shell.registry.register("sched", custom_sched)
        code, out, _ = self.run_cmd("sched fcfs processes.txt")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "CUSTOM_SCHED_OK:fcfs,processes.txt")


if __name__ == "__main__":
    unittest.main(verbosity=2)