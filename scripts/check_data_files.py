#!/usr/bin/env python3
"""Block member data and other private files from being committed.

Spreadsheets, databases, member exports, environment files, private keys and
office-suite lock files don't belong in a repository. This repo once leaked a
Blu Print member export and a copy of the live database this way.

Usage:
  python scripts/check_data_files.py            check every tracked file (CI)
  python scripts/check_data_files.py --staged   check files being committed (pre-commit hook)

Exit code 1 lists the offending files. To allow a specific file on purpose,
add its exact path to scripts/data_files_allowlist.txt with a reason.
"""
import fnmatch
import os
import subprocess
import sys

BLOCKED = [
    # spreadsheets and documents that usually hold rosters
    ("*.xls", "spreadsheet"), ("*.xlsx", "spreadsheet"), ("*.xlsm", "spreadsheet"),
    ("*.ods", "spreadsheet"), ("*.numbers", "spreadsheet"),
    # databases and dumps
    ("*.sqlite", "database"), ("*.sqlite3", "database"), ("*.db", "database"),
    ("*.sqlite3-journal", "database"), ("*.dump", "database dump"), ("*.sql.gz", "database dump"),
    ("*.bak", "backup file"),
    # known member exports
    ("*ResultsGrid*", "Blu Print export"), ("*ChapterList*", "Blu Print export"),
    ("*PIAByChapter*", "Blu Print PIA export"), ("*_export*.csv", "data export"),
    ("*roster*.csv", "member roster"), ("*members*.csv", "member list"), ("*contacts*.csv", "contact list"),
    # secrets
    (".env", "environment file with secrets"), (".env.*", "environment file with secrets"),
    ("*.pem", "private key or certificate"), ("*.key", "private key"), ("*.p12", "certificate bundle"),
    ("*.pfx", "certificate bundle"), ("id_rsa*", "SSH key"), ("id_ed25519*", "SSH key"),
    # editor and office lock files (they reveal user and machine names)
    (".~lock.*", "office lock file"), ("~$*", "office lock file"),
]
ALWAYS_OK = {".env.example", ".env.sample", ".env.template"}
TEMPLATE_SUFFIXES = (".example", ".sample", ".template")   # e.g. .env.production.example
ALLOWLIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_files_allowlist.txt")


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def _allowlist():
    try:
        with open(ALLOWLIST, encoding="utf-8") as fh:
            return {ln.split("#", 1)[0].strip() for ln in fh if ln.split("#", 1)[0].strip()}
    except FileNotFoundError:
        return set()


def problems(paths, allowed=frozenset()):
    found = []
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if path in allowed or name in ALWAYS_OK or name.lower().endswith(TEMPLATE_SUFFIXES):
            continue
        for pattern, why in BLOCKED:
            if fnmatch.fnmatch(name.lower(), pattern.lower()):
                found.append((path, why))
                break
    return found


def main(argv):
    staged = "--staged" in argv
    if staged:
        paths = _git("diff", "--cached", "--name-only", "--diff-filter=ACR").splitlines()
    else:
        paths = _git("ls-files").splitlines()
    found = problems(paths, _allowlist())
    if not found:
        print("Data file check passed.")
        return 0
    print("Blocked: these files look like member data, databases or secrets and must not be committed:\n")
    for path, why in found:
        print(f"  {path}  ({why})")
    if staged:
        print("\nUnstage them with:  git restore --staged <file>")
    else:
        print("\nRemove them with:  git rm --cached <file>  (and add the pattern to .gitignore)")
    print("If a file is truly safe (sample data, no real people), add its path to "
          "scripts/data_files_allowlist.txt with a reason.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
