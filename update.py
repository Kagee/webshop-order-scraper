#! /usr/bin/env python3
import sys
import os
import subprocess
from shutil import which

def find_pythons():
    python = None
    pythons = [
        "python3.9",
        "python3.10",
        "python3.11",
        "python3.12",
        "python3.13",
        "python3.14",
    ]
    for pyt in pythons:
        if which(pyt):
            python = pyt
    if not python:
        print(
            "Failed to find a compatible python! Looked for:"
            f" {', '.join(pythons)}"
        )
        sys.exit(1)
    return python

if sys.version_info.major < 3 or sys.version_info.minor < 9:
    print(f"Requires Python 3.9 or newer, this is %s.%s" % (sys.version_info.major, sys.version_info.minor))
    newest_python = find_pythons()
    print("Found %s, reloading..." %(newest_python,))
    subprocess.run([newest_python, __file__], check=False)
    sys.exit(0)

from importlib.util import find_spec

if "VIRTUAL_ENV" not in os.environ and not os.access("./venv", os.R_OK):
    venv_loader = find_spec("venv")
    if not venv_loader:
        print(
            "Failed to find venv module using"
            f" {sys.executable} ({sys.version_info.major}.{sys.version_info.minor})."
            " Please install it using your system package manager."
        )
        sys.exit(1)

    venv = input("No ./venv found. Create? (Y/n): ")
    if venv.lower() == "y" or venv == "":
        from venv import create
        create("./venv", with_pip=True)
        print("Please activate the venv,then re-run the script")
        sys.exit()

if "VIRTUAL_ENV" not in os.environ:
    print(
        "Please activate the python virtual envirionment before running this"
        " script."
    )
    sys.exit(1)

print("git pull")
subprocess.run(["git", "pull"], check=False)

print("update pip")
subprocess.run(
   [sys.executable, "-m", "pip", "install", "-U", "pip"],
   check=False,
)

print("pip install")
subprocess.run(
   [sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"],
   check=False,
)

print("Nuke database")
subprocess.run([sys.executable, "sudo-nuke-db.py"], check=False)
