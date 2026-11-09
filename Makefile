# Makefile for CmpSc 123 MiniShell (All 4 Members Integrated)
PYTHON := python3

.PHONY: all run test demo clean

all: test
	@echo "All 4 modules verified and ready! Run 'python3 minishell.py' or 'make run' to start."

run:
	$(PYTHON) minishell.py

demo:
	$(PYTHON) minishell.py demo.msh

test:
	$(PYTHON) -m py_compile minishell.py scheduler.py deadlock.py report.py grep_cmd.py util.py
	$(PYTHON) test_shell_lead.py
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m unittest -v test_minishell

clean:
	rm -rf __pycache__ tests/__pycache__ *.pyc
