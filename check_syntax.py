#!/usr/bin/env python3
"""Check Python syntax for all project files."""

import os
import py_compile
import sys

PROJECT_DIRS = ['client', 'server', 'shared', 'config']

def check_file(filepath):
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"OK: {filepath}")
        return True
    except py_compile.PyCompileError as e:
        print(f"ERROR: {filepath}")
        print(f"  {e}")
        return False

def main():
    all_ok = True
    for dirname in PROJECT_DIRS:
        if not os.path.isdir(dirname):
            continue
        for filename in os.listdir(dirname):
            if filename.endswith('.py'):
                filepath = os.path.join(dirname, filename)
                if not check_file(filepath):
                    all_ok = False
    
    # Also check main.py
    if os.path.isfile('main.py'):
        if not check_file('main.py'):
            all_ok = False
    
    if all_ok:
        print("\nAll files have valid syntax")
        return 0
    else:
        print("\nSome files have syntax errors")
        return 1

if __name__ == '__main__':
    sys.exit(main())
