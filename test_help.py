import sys
import os

# Set up to run main.py with --help
sys.argv = ['main.py', '--help']

# Import and call main
exec(open('main.py').read())
