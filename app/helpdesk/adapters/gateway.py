"""Adaptador concreto: fala com o gateway de IA (LiteLLM) pela API da OpenAI.

O gateway expõe uma API compatível com Chat Completions. Enviamos o nome lógico da
capacidade como `model`; é o LiteLLM que resolve o modelo físico, o provider, os
fallbacks, os timeouts e os retries. A aplicação usa uma única virtual key e nunca
vê chaves reais de provider.

Este módulo é a ÚNICA peça do helpdesk que conhece um SDK de LLM. Ele importa apenas
a porta (`LLMPort`) e a biblioteca `openai`; não depende de nenhuma feature nem da
configuração — tudo o que precisa chega pelo construtor (injeção de dependência).
"""

from openai import OpenAI

from ..ports import LLMPort


class GatewayLLM(LLMPort):
    """Implementação de `LLMPort` que roteia tudo pelo gateway LiteLLM."""

    def __init__(self, base_url: str, api_key: str, max_output_tokens: int):
        # `base_url` aponta para o gateway (ex.: http://gateway:4000). `api_key` é a
        # virtual key do gateway — a aplicação não guarda chaves de provider.
        # max_retries=0: quem faz retry/backoff/fallback é o gateway. Deixar o SDK
        # também tentando multiplicaria as chamadas ao provider.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self._max_output_tokens = max_output_tokens

    def generate(self, capability: str, content: str) -> str:
        # O provider simulado reconhece a tarefa pela primeira linha "TASK: <nome>".
        # O nome lógico da capacidade é também o nome da tarefa, então reaproveitamos.
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=[{"role": "user", "content": f"TASK: {capability}\n{content}"}],
        )
        return response.choices[0].message.content
