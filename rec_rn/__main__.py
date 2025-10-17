"""Ponto de entrada para executar o REC RN via `python -m rec_rn`."""

from .console import run_console


def main() -> None:
    """Inicializa a aplicação de console."""

    run_console()


if __name__ == "__main__":
    main()
