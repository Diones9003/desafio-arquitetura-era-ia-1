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

# Timeout explícito das features SÍNCRONAS (F1 classify, F4 extract), em segundos.
# É o teto do lado da aplicação: mesmo que o gateway demore, a chamada não fica
# pendurada além disso. Combinado com o timeout por modelo no gateway (que corta o
# primário travado e cai no fallback), garante resposta — sucesso ou erro — em até 15s.
SYNC_TIMEOUT = 15.0

# Sugestão de intervalo (segundos) que o cliente deve esperar antes de consultar o
# status de um relatório assíncrono (header Retry-After na resposta 202 da F3).
REPORT_RETRY_AFTER = 5

TICKETS_FILE = os.environ.get("TICKETS_FILE", "/data/tickets.jsonl")
TICKETS_PER_CALL = 150
