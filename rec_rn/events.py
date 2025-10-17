"""Modelos e utilitários para eventos do REC RN."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, List


class EventSeverity(Enum):
    """Nível de severidade de um evento monitorado."""

    INFO = "informativo"
    WARNING = "alerta"
    CRITICAL = "critico"


@dataclass(slots=True)
class Event:
    """Representa um evento capturado pela operação."""

    source: str
    description: str
    severity: EventSeverity
    timestamp: datetime = field(default_factory=datetime.utcnow)
    tags: List[str] = field(default_factory=list)

    def format_summary(self) -> str:
        """Retorna uma string resumida para uso na CLI."""

        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        tag_str = f" [{' | '.join(self.tags)}]" if self.tags else ""
        return f"{ts} | {self.severity.value.upper():<9} | {self.source}: {self.description}{tag_str}"


def seed_events(sources: Iterable[str]) -> List[Event]:
    """Gera uma lista inicial de eventos simulados para testes."""

    severities = [EventSeverity.INFO, EventSeverity.WARNING, EventSeverity.CRITICAL]
    templates = [
        "Check-in concluído",
        "Anomalia detectada",
        "Botão de pânico acionado",
    ]

    seeded: List[Event] = []
    for idx, source in enumerate(sources):
        severity = severities[idx % len(severities)]
        description = templates[idx % len(templates)]
        tags = [f"canal:{source.lower()}", f"seq:{idx+1}"]
        seeded.append(Event(source=source, description=description, severity=severity, tags=tags))
    return seeded
