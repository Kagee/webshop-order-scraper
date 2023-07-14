#! /usr/bin/env python3

from bootstrap import python_checks

python_checks()

# pylint: disable=wrong-import-position,wrong-import-order

import subprocess
import sys

if len(sys.argv) == 1 or sys.argv[1] != "no-git":
    print("git pull")
    subprocess.run(["git", "pull"], check=False)

print("upgrade pip")
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

print("pip install")
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
