"""Console interativo simples para o REC RN."""

from __future__ import annotations

import itertools
import random
from datetime import datetime
from typing import Iterable, List

from .events import Event, EventSeverity, seed_events


def _generate_event(counter: itertools.count) -> Event:
    sources = ["DRONE", "CÂMERA", "PONTO FIXO", "VIATURA"]
    descriptions = [
        "Movimentação suspeita detectada",
        "Equipamento sem resposta",
        "Operador solicitou apoio",
        "Patrulha confirmou perímetro",
    ]
    severity = random.choices(
        population=[EventSeverity.INFO, EventSeverity.WARNING, EventSeverity.CRITICAL],
        weights=[0.5, 0.3, 0.2],
        k=1,
    )[0]
    idx = next(counter)
    source = random.choice(sources)
    description = random.choice(descriptions)
    tags = [f"auto:{idx}"]
    return Event(source=source, description=description, severity=severity, timestamp=datetime.utcnow(), tags=tags)


def run_console(seed_sources: Iterable[str] | None = None) -> None:
    """Executa o loop principal da CLI."""

    if seed_sources is None:
        seed_sources = ("DRONE", "PONTO FIXO", "CÂMERA")

    history: List[Event] = seed_events(seed_sources)
    generator_counter = itertools.count(start=len(history) + 1)

    menu = (
        "\n=== REC RN ===\n"
        "1 - Listar eventos\n"
        "2 - Gerar evento simulado\n"
        "3 - Limpar histórico\n"
        "0 - Sair\n"
        "Escolha uma opção: "
    )

    while True:
        try:
            choice = input(menu).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando REC RN. Até breve!")
            break

        if choice == "1":
            if not history:
                print("Nenhum evento registrado.")
                continue
            print("\n-- Histórico de eventos --")
            for event in history:
                print(event.format_summary())
        elif choice == "2":
            event = _generate_event(generator_counter)
            history.append(event)
            print("Evento gerado:")
            print(event.format_summary())
        elif choice == "3":
            history.clear()
            print("Histórico limpo.")
        elif choice == "0":
            print("Encerrando REC RN. Até breve!")
            break
        else:
            print("Opção inválida. Tente novamente.")
