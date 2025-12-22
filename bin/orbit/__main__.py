"""
Entry point for running orbit as a module: python -m orbit
"""

import sys
from pathlib import Path

# Add the project root to sys.path so that 'bin.orbit' can be imported
# when this module is run directly
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from bin.orbit.cli import main

if __name__ == "__main__":
    main()

