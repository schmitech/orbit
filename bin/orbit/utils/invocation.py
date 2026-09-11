"""
How to invoke the ORBIT CLI from a shell.

The CLI is not installed on PATH - it is reached through the wrapper scripts
in bin/ - so runtime hints must name the wrapper for the current platform
rather than a bare `orbit`.
"""

import os


def cli_command(*args: str) -> str:
    """
    Build a copy-pasteable CLI invocation.

    Args:
        *args: Subcommand and flags, e.g. cli_command("stop", "--force")

    Returns:
        The full command, e.g. "./bin/orbit.sh stop --force"
    """
    wrapper = "bin\\orbit.bat" if os.name == "nt" else "./bin/orbit.sh"
    return " ".join((wrapper, *args))
