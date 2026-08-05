#!/usr/bin/env python3
"""Fix relative imports to absolute imports in project files."""

import os
import re

PROJECT_DIRS = ['client', 'server', 'shared']
REPLACEMENTS = [
    (r'from \.\.config import', 'from config import'),
    (r'from \.\.shared import', 'from shared import'),
    (r'from \.\.client import', 'from client import'),
    (r'from \.\.server import', 'from server import'),
    (r'from \.connection import', 'from client.connection import'),
]

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    for pattern, replacement in REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Fixed: {filepath}")
    else:
        print(f"No changes: {filepath}")

def main():
    for dirname in PROJECT_DIRS:
        if not os.path.isdir(dirname):
            continue
        for filename in os.listdir(dirname):
            if filename.endswith('.py'):
                filepath = os.path.join(dirname, filename)
                fix_file(filepath)

if __name__ == '__main__':
    main()
