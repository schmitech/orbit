#!/usr/bin/env python3
"""
Main entry point for Orbit CLI
"""

from orbit_cli.cli import OrbitCLI


def main():
    """Main entry point"""
    cli = OrbitCLI()
    cli.run()


if __name__ == "__main__":
    main() 