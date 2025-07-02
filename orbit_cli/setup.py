#!/usr/bin/env python3
"""
Setup script for ORBIT CLI.

This setup.py is provided for backward compatibility.
Modern installation should use pyproject.toml.
"""

import os
import sys
from pathlib import Path
from setuptools import setup, find_packages

# Add the orbit_cli directory to Python path to import version
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from orbit_cli.__version__ import __version__, __author__, __description__, __url__
except ImportError:
    # Fallback if __version__.py is not available
    __version__ = "1.0.0"
    __author__ = "Remsy Schmilinsky"
    __description__ = "ORBIT Control CLI - Enterprise-grade Open Inference Server management"
    __url__ = "https://github.com/schmitech/orbit"

# Read the README file
README_PATH = Path(__file__).parent / "README.md"
if README_PATH.exists():
    with open(README_PATH, "r", encoding="utf-8") as f:
        long_description = f.read()
else:
    long_description = __description__

# Core dependencies
INSTALL_REQUIRES = [
    "requests>=2.32.0",
    "rich>=13.0.0",
    "psutil>=5.9.0",
    "pyyaml>=6.0.2",
    "keyring>=25.6.0",
    "cryptography>=41.0.0",
    "python-dateutil>=2.8.0",
    "python-dotenv>=1.0.1",
]

# Optional dependencies
EXTRAS_REQUIRE = {
    "dev": [
        "pytest>=7.0.0",
        "pytest-cov>=4.0.0",
        "pytest-mock>=3.10.0",
        "black>=23.0.0",
        "isort>=5.12.0",
        "flake8>=6.0.0",
        "mypy>=1.0.0",
        "pre-commit>=3.0.0",
        "twine>=4.0.0",
        "build>=0.10.0",
    ],
    "test": [
        "pytest>=7.0.0",
        "pytest-cov>=4.0.0",
        "pytest-mock>=3.10.0",
        "responses>=0.23.0",
    ],
    "docs": [
        "sphinx>=6.0.0",
        "sphinx-rtd-theme>=1.2.0",
        "myst-parser>=1.0.0",
    ],
}

# Add 'all' extra that includes everything
EXTRAS_REQUIRE["all"] = list(set(
    dep for deps in EXTRAS_REQUIRE.values() for dep in deps
))

setup(
    name="orbit-cli",
    version=__version__,
    author=__author__,
    author_email="info@schmitech.ca",
    description=__description__,
    long_description=long_description,
    long_description_content_type="text/markdown",
    url=__url__,
    project_urls={
        "Documentation": "https://github.com/schmitech/orbit/tree/main/docs",
        "Repository": "https://github.com/schmitech/orbit",
        "Bug Tracker": "https://github.com/schmitech/orbit/issues",
        "Changelog": "https://github.com/schmitech/orbit/blob/main/CHANGELOG.md",
    },
    packages=find_packages(
        exclude=["tests", "tests.*", "docs", "docs.*"]
    ),
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
    entry_points={
        "console_scripts": [
            "orbit=orbit_cli.main:main",
            "orbit-cli=orbit_cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP :: HTTP Servers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Systems Administration",
        "Topic :: Utilities",
    ],
    keywords=[
        "orbit",
        "cli",
        "ai",
        "inference",
        "server",
        "management",
        "api",
        "enterprise",
    ],
    license="Apache-2.0",
    zip_safe=False,
    # Ensure we include all necessary files
    package_data={
        "orbit_cli": [
            "*.txt",
            "*.md",
            "*.yaml",
            "*.yml",
            "*.json",
        ],
    },
) 