# MiniShell — Member 1 (Shell Lead) Implementation & Integration Guide

## Overview of the Shell Lead Package

This package delivers the complete **Member 1: Shell Lead** responsibilities for the **CmpSc 123 Project: MiniShell** in Python 3 (`minishell.py`), alongside an automated verification suite (`test_shell_lead.py`). It implements every required feature and bonus item in **Module 1: Shell Core (30 points)** and provides the command integration dispatcher for **Module 2 (`sched`)**, **Module 3 (`deadlock`)**, **Module 4 (`compare`)**, and **Text Search (`grep`)**.

| Module 1 Rubric Item | Points | Status | Implementation Highlights |
| :--- | :---: | :---: | :--- |
| **File & Directory Built-ins** | 8 pts | Complete | `pwd`, `cd`, `ls` (`-l`, `-a`), `mkdir` (`-p`), `rmdir`, `touch`, `cp` (`-r`), `mv`, `rm` (`-r`, `-f`), `cat` (`-n`), `echo`, `clear`, `history`, `help`, `exit` |
| **Permissions (`chmod` & `ls -l`)** | Included in 8 pts | Complete | Numeric octal modes (`chmod 755 file`, `chmod 640 file`) and symbolic modes (`u+x`, `go-w`) with symbolic (`-rwxr-xr-x`) and octal (`0755`) display in `ls -l` |
| **Stream Redirection** | 7 pts | Complete | `>` (overwrite), `>>` (append), `<` (stdin), `2>` (stderr), `2>>` (stderr append), `2>&1` (merge stderr into stdout), and `1>&2` |
| **Pipes (`\|`)** | 5 pts | Complete | Two-stage and multi-stage pipelines (`ls \| grep txt`, `cat file.txt \| grep pattern \| cat -n`) connecting `stdout` to `stdin` |
| **Variables & Conditionals** | 5 pts | Complete | `NAME=value`, `$NAME`, `${NAME}`, `$?`, `env`, `export`, `unset`, `&&`, `\|\|`, `;`, plus Bonus `if / then / elif / else / fi` |
| **Text Search (`grep`)** | 3 pts | Complete | Substring matching plus Bonus regex patterns (`.`, `[a-z]`, `*`, `+`, `?`, `\` escaping, capturing groups `(...)`) and flags (`-i`, `-n`, `-v`, `-c`, `-o`, `-F`, `-E`, `--groups`) |
| **Error Handling** | 2 pts | Complete | Non-crashing execution loop with descriptive `stderr` messages and non-zero exit codes for unknown commands, missing files, bad modes, and syntax errors |
| **Final Command Integration** | Role Duty | Complete | Auto-discovers `scheduler.py` (`sched`), `deadlock.py` (`deadlock`), and `report.py` (`compare`) or uses built-in CLI validation adapters |

## Build and Run Instructions

MiniShell requires **Python 3.8+** using only the Python standard library (`os`, `sys`, `stat`, `shutil`, `re`, `subprocess`, `io`), complying with project rules (no external scheduling or shell libraries required).

### 1. Start Interactive Shell (`minishell>` prompt)

```bash
python3 minishell.py
```

Type commands at the `minishell>` prompt and type `exit` (or press `Ctrl+D`) to quit.

### 2. Run a Single Command Line (`-c`)

```bash
python3 minishell.py -c "NAME=Ana; echo Hello \$NAME"
```

### 3. Run the Automated Verification Suite

```bash
python3 test_shell_lead.py
```

## Complete Command Reference

| Category | Command / Syntax | Description & Example |
| :--- | :--- | :--- |
| **Navigation & Listing** | `pwd` | Print current working directory (`pwd`) |
| **Navigation & Listing** | `cd [dir \| ~ \| -]` | Change directory (`cd src`, `cd ..`, `cd -`) |
| **Navigation & Listing** | `ls [-l] [-a] [path...]` | List directory contents; `-l` shows permissions (`ls -l`) |
| **Directory Management** | `mkdir [-p] <dir...>` | Create directory or nested directories (`mkdir -p a/b/c`) |
| **Directory Management** | `rmdir <dir...>` | Remove empty directory (`rmdir old_folder`) |
| **File Operations** | `touch <file...>` | Create empty file or update timestamp (`touch notes.txt`) |
| **File Operations** | `cp [-r] <src...> <dst>` | Copy files or directories (`cp notes.txt backup.txt`) |
| **File Operations** | `mv <src...> <dst>` | Move or rename files/directories (`mv backup.txt archive.txt`) |
| **File Operations** | `rm [-r] [-f] <target...>` | Remove files or directories (`rm -rf temp_dir`) |
| **File Operations** | `cat [-n] [file...]` | Print file contents or read piped stdin (`cat -n notes.txt`) |
| **Permissions** | `chmod <octal> <file...>` | Set numeric or symbolic file mode (`chmod 755 run.sh`) |
| **Variables** | `NAME=value` | Assign shell/environment variable (`USER_ROLE=ShellLead`) |
| **Variables** | `echo [-n] [args...]` | Print text and expanded variables (`echo $USER_ROLE`) |
| **Variables** | `env` / `export` / `unset` | List all variables, export variables, or remove a variable |
| **Redirection** | `>`, `>>`, `<`, `2>`, `2>&1` | Redirect stdout, stdin, and stderr (`ls > out.txt 2>&1`) |
| **Pipes** | `cmd1 \| cmd2 [\| cmd3...]` | Connect stdout of `cmd1` to stdin of `cmd2` (`ls \| grep txt`) |
| **Conditionals** | `cmd1 && cmd2` | Run `cmd2` only if `cmd1` succeeded (exit code `0`) |
| **Conditionals** | `cmd1 \|\| cmd2` | Run `cmd2` only if `cmd1` failed (exit code `!= 0`) |
| **Conditionals** | `cmd1 ; cmd2` | Run `cmd1` followed unconditionally by `cmd2` |
| **Bonus Control Flow** | `if <c>; then <t>; else <e>; fi` | Conditional branch execution (`if true; then echo OK; fi`) |
| **Text Search** | `grep [-invcoFE] [--groups] <pat> [file...]` | Search lines matching substring or regex (`grep '^[a-z]+' f.txt`) |
| **Module 2 Integration** | `sched <algo> [--quantum N] <file>` | Dispatch process scheduler (`sched rr --quantum 4 samples/processes1.txt`) |
| **Module 3 Integration** | `deadlock <detect\|banker> <file>` | Dispatch deadlock simulator (`deadlock detect samples/system_deadlock.txt`) |
| **Module 4 Integration** | `compare [--quantum N] <file>` | Compare all 6 scheduling algorithms (`compare --quantum 4 samples/processes1.txt`) |

## How Teammates Integrate Modules 2, 3, and 4

`minishell.py` includes an `IntegrationRegistry` that automatically hooks up Member 2's, Member 3's, and Member 4's code with zero edits required to the core parser, pipe engine, or redirection engine. Because `minishell.py` passes `stdin`, `stdout`, and `stderr` stream objects into every handler, pipes and file redirections (`sched fcfs samples/processes1.txt > results.txt` or `deadlock banker samples/system_safe.txt | grep SAFE`) work automatically on teammate commands.

### Option A: Drop-in Module Files (Zero Configuration)

**Member 2 (Scheduler Lead):** Create `scheduler.py` in the same folder as `minishell.py` and define:

```python
def run_sched(args, stdin, stdout, stderr) -> int:
    # args is a list of strings, e.g. ['rr', '--quantum', '4', 'processes.txt']
    # Write output using stdout.write(...) and errors using stderr.write(...)
    # Return 0 on success, non-zero on error
    return 0
```

**Member 3 (Resources Lead):** Create `deadlock.py` in the same folder as `minishell.py` and define:

```python
def run_deadlock(args, stdin, stdout, stderr) -> int:
    # args is a list of strings, e.g. ['detect', 'system.txt'] or ['banker', 'system.txt']
    # Write output using stdout.write(...) and errors using stderr.write(...)
    # Return 0 on success, non-zero on error
    return 0
```

**Member 4 (Docs & Testing Lead):** Create `report.py` in the same folder as `minishell.py` and define:

```python
def run_compare(args, stdin, stdout, stderr) -> int:
    # args is a list of strings, e.g. ['--quantum', '4', 'samples/processes1.txt']
    # Write output using stdout.write(...) and errors using stderr.write(...)
    # Return 0 on success, non-zero on error
    return 0
```

### Option B: Programmatic Registration

Teammates can also register any custom handler function directly on a `MiniShell` instance:

```python
from minishell import MiniShell

shell = MiniShell()
shell.registry.register("sched", my_scheduler_function)
shell.registry.register("deadlock", my_deadlock_function)
shell.registry.register("compare", my_compare_function)
shell.run_repl()
```

## Live Demo Script (Copy-Paste Session for Grading)

During the 10–15 minute live group demo, run `python3 minishell.py` and paste these commands to showcase every Module 1 requirement, bonus item, and error case:

```bash
# 1. File & Directory Built-ins + Permissions (chmod & ls -l)
pwd
mkdir demo_dir && cd demo_dir
touch report.txt notes.txt script.sh image.png
chmod 755 script.sh
chmod 640 report.txt
ls -l

# 2. Stream Redirection (>, >>, <, 2>, 2>&1)
echo "Process_A arrival=0 burst=5" > report.txt
echo "Process_B arrival=2 burst=3" >> report.txt
cat < report.txt
cat missing_file.txt 2> error.log
cat error.log

# 3. Pipes (|) and Text Search (grep with Bonus Regex)
ls | grep txt
grep 'Process_[A-Z] arrival=[0-9]+' report.txt

# 4. Variables (NAME=value, $NAME, env) & Conditionals (&&, ||, ;, Bonus if/then/else)
COURSE=CmpSc123
ROLE="Shell Lead"
echo "Course: $COURSE | Role: $ROLE"
true && echo "Success branch triggered"
false || echo "Fallback branch triggered"
if grep Process_A report.txt > /dev/null; then echo "Found Process_A!"; else echo "Missing!"; fi

# 5. Error Handling Demonstration (Unknown command, missing file, bad chmod mode)
unknown_command_test
chmod 999 report.txt
cd .. && rm -rf demo_dir
exit
```
