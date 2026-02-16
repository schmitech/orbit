"""
Command handler modules for the ORBIT CLI.
"""

from abc import ABC, abstractmethod
import argparse


class BaseCommand(ABC):
    """
    Base class for all command handlers.
    
    This abstract base class defines the interface that all command handlers
    must implement, following the Command pattern and Single Responsibility Principle.
    """
    
    @abstractmethod
    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """
        Add command-specific arguments to the parser.
        
        Args:
            parser: The argument parser to add arguments to
        """
        pass
    
    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """
        Execute the command with the given arguments.
        
        Args:
            args: Parsed command arguments
            
        Returns:
            Exit code (0 for success, non-zero for error)
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the command name."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Return the command description."""
        pass
