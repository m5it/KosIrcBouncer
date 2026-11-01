import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.argv = ['main.py', '--help']
exec(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'main.py')).read())
