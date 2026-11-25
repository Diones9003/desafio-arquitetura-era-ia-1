"""Configuração da aplicação: apenas o endereço do gateway e nomes lógicos.

A aplicação não conhece mais provedores, URLs de provider nem nomes de modelos
físicos de cada provider. Ela fala só com o gateway, usando uma virtual
key, e se refere às tarefas por capacidades lógicas. Trocar o modelo por trás de uma
capacidade é mudança de configuração do gateway, não de código da aplicação.
"""

import os

# Endereço do gateway de IA (LiteLLM) e a virtual key usada pela aplicação.
GATEWAY_URL = os.environ["GATEWAY_URL"]
GATEWAY_API_KEY = os.environ["GATEWAY_API_KEY"]

# Capacidades lógicas conhecidas pela aplicação. O mapeamento capacidade -> modelo
# físico, fallbacks, timeouts e retries vive no gateway (gateway/config.yaml).
CLASSIFY = "classify"
SUGGEST = "suggest"
TOPICS = "topics"
EXTRACT = "extract"

MAX_OUTPUT_TOKENS = 2000

TICKETS_FILE = os.environ.get("TICKETS_FILE", "/data/tickets.jsonl")
TICKETS_PER_CALL = 150
