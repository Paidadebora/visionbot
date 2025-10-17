# REC RN

`REC RN` é um protótipo inicial focado em demonstrar interações rápidas entre
operadores de segurança e dispositivos de campo em um ambiente desktop Windows.
O objetivo é fornecer uma base enxuta para testes de usabilidade, validação de
fluxos de comunicação e coleta de feedback antes de evoluir para integrações
mais complexas.

## Objetivos do MVP

- **Centralizar alertas** provenientes de múltiplos pontos de coleta em uma
  interface simples de linha de comando.
- **Registrar eventos** com metadados suficientes para análises posteriores e
  reexecução de cenários de teste.
- **Permitir expansão modular**, facilitando a substituição de fontes de dados
  simuladas por integrações reais em iterações futuras.

## Estrutura do repositório

```
rec_rn/
  __init__.py        # Inicializa o pacote
  __main__.py        # Ponto de entrada "python -m rec_rn"
  console.py         # Loop principal da simulação e CLI
  events.py          # Modelos simples de eventos e utilitários
```

## Como executar

1. Certifique-se de ter o Python 3.10+ instalado.
2. No diretório do projeto, execute:
   ```bash
   python -m rec_rn
   ```
3. Siga as instruções apresentadas na CLI para iniciar ou encerrar sessões de
   monitoramento e revisar o histórico de eventos capturados.

## Próximos passos sugeridos

- Integrar fontes reais (ex.: telemetria, câmeras, botões de pânico) para
  substituir os geradores simulados.
- Criar interface gráfica ou painel web para visualização em tempo real.
- Adicionar mecanismos de autenticação e perfis de acesso diferenciados.

Este repositório está totalmente dedicado ao **REC RN**, sem vínculo com
projetos anteriores.
