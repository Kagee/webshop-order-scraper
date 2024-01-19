#! /usr/bin/env python3
# ruff: noqa: E402, S603
from bootstrap import python_checks

python_checks()

# pylint: disable=wrong-import-position,wrong-import-order
import subprocess
import sys

nuke = input("Upgrade pip? (Y/n): ")
if nuke.lower() != "n":
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--require-virtualenv",
            "--no-user",
            "--upgrade",
            "pip",
        ],
        check=False,
    )

nuke = input("Pip install? (Y/n): ")
if nuke.lower() != "n":
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--require-virtualenv",
            "--no-user",
            "--upgrade",
            "-r",
            "requirements-dev.txt",
        ],
        check=False,
    )
