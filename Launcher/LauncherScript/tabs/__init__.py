# tabs/__init__.py - Tab classes for MSFSPyScriptManager

from .base import Tab
from .script_tab import ScriptTab
from .perf_tab import PerfTab
from .markdown_tab import MarkdownTab
from .command_line_tab import CommandLineTab

__all__ = ['Tab', 'ScriptTab', 'PerfTab', 'MarkdownTab', 'CommandLineTab']
