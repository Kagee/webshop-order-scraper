#! /usr/bin/env python3
import sys
import subprocess

print("git pull")
subprocess.run(["git", "pull"], check=False)

print("git pull")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"],
    check=False,
)

print("Nuke database")
subprocess.run([sys.executable, "sudo-nuke-db.py"], check=False)
