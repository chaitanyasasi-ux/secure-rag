"""
Patches applied at startup for cross-platform compatibility.
On Linux (production), portalocker works natively.
On Windows (development), we use stub modules.
"""
import sys
import platform

def apply_patches() -> None:
    if platform.system() == "Windows":
        # Windows requires pywin32 for portalocker
        # If not available, create minimal stubs
        try:
            import pywintypes
        except ImportError:
            from unittest.mock import MagicMock
            sys.modules['pywintypes'] = MagicMock()
            sys.modules['win32con'] = MagicMock()
            sys.modules['win32file'] = MagicMock()
            sys.modules['win32security'] = MagicMock()
            sys.modules['winerror'] = MagicMock()