#!/usr/bin/env python3
"""
reboot_system.py - Safely request a system reboot from Python.

Features:
- Requires explicit confirmation via --yes (or use --dry-run for testing).
- Checks for root privileges unless --dry-run is used.
- Tries multiple mechanisms in order:
  1) systemctl reboot
  2) reboot (or /sbin/reboot)
  3) shutdown -r now
- Provides clear messaging and exit codes.

Usage examples:
  # Preview actions without rebooting
  ./reboot_system.py --dry-run

  # Actually reboot (must be run as root)
  sudo ./reboot_system.py --yes

Note: The process will typically terminate immediately upon successful reboot invocation.
"""

import argparse
import os
import shutil
import subprocess
import sys
from typing import List, Optional


def is_root() -> bool:
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        # Non-POSIX; fall back to environment heuristics
        return os.name == "nt" and "USERNAME" in os.environ and os.environ.get("USERNAME") == "Administrator"


def find_command(candidates: List[str]) -> Optional[str]:
    for c in candidates:
        path = shutil.which(c)
        if path:
            return path
    return None


def run(cmd: List[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    if dry_run:
        print(f"[DRY-RUN] Would run: {' '.join(cmd)}")
        # Simulate success
        class Dummy:
            returncode = 0
        return Dummy()  # type: ignore[return-value]
    print(f"Executing: {' '.join(cmd)}")
    return subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)


def attempt_reboot(dry_run: bool = False) -> int:
    # 1) systemctl reboot
    systemctl = find_command(["systemctl"])  # rely on PATH
    if systemctl:
        result = run([systemctl, "reboot"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"systemctl reboot failed with code {result.returncode}")

    # 2) reboot (try PATH then common absolute path)
    reboot_cmd = find_command(["reboot"]) or ("/sbin/reboot" if os.path.exists("/sbin/reboot") else None)
    if reboot_cmd:
        result = run([reboot_cmd, "now"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"reboot command failed with code {result.returncode}")

    # 3) shutdown -r now
    shutdown_cmd = find_command(["shutdown"]) or ("/sbin/shutdown" if os.path.exists("/sbin/shutdown") else None)
    if shutdown_cmd:
        result = run([shutdown_cmd, "-r", "now"], dry_run=dry_run)
        if result.returncode == 0:
            return 0
        else:
            print(f"shutdown -r now failed with code {result.returncode}")

    print("No suitable reboot method succeeded or is available.")
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Request a system reboot safely.")
    parser.add_argument("--yes", action="store_true", help="Confirm you really want to reboot now.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without rebooting.")

    args = parser.parse_args(argv)

    if not args.dry_run and not args.yes:
        print("Refusing to reboot without explicit confirmation. Re-run with --yes, or use --dry-run to test.")
        return 2

    if not args.dry_run and not is_root():
        print("This script must be run as root to perform a reboot. Try: sudo ./reboot_system.py --yes")
        return 3

    if args.dry_run:
        print("Dry-run mode: no changes will be made.")

    print("System reboot requested")
    return attempt_reboot(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
