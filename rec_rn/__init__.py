"""Pacote principal do projeto REC RN."""

from .events import Event, EventSeverity
from .console import run_console

__all__ = ["Event", "EventSeverity", "run_console"]
