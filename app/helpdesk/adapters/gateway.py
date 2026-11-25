"""Adaptador concreto: fala com o gateway de IA (LiteLLM) pela API da OpenAI.

O gateway expõe uma API compatível com Chat Completions. Enviamos o nome lógico da
capacidade como `model`; é o LiteLLM que resolve o modelo físico, o provider, os
fallbacks, os timeouts e os retries. A aplicação usa uma única virtual key e nunca
vê chaves reais de provider.

Este módulo é a ÚNICA peça do helpdesk que conhece um SDK de LLM. Ele importa apenas
a porta (`LLMPort`) e a biblioteca `openai`; não depende de nenhuma feature nem da
configuração — tudo o que precisa chega pelo construtor (injeção de dependência).
"""

from typing import Iterator

from openai import OpenAI

from ..ports import LLMPort


class GatewayLLM(LLMPort):
    """Implementação de `LLMPort` que roteia tudo pelo gateway LiteLLM."""

    def __init__(self, base_url: str, api_key: str, max_output_tokens: int,
                 default_timeout: float):
        # `base_url` aponta para o gateway (ex.: http://gateway:4000). `api_key` é a
        # virtual key do gateway — a aplicação não guarda chaves de provider.
        # max_retries=0: quem faz retry/backoff/fallback é o gateway. Deixar o SDK
        # também tentando multiplicaria as chamadas ao provider.
        # default_timeout: teto explícito de tempo em cada chamada (segundos). É a
        # garantia, no lado da aplicação, de que nenhuma feature síncrona fica
        # pendurada quando o provider trava — além do timeout do próprio gateway.
        self._client = OpenAI(api_key=api_key, base_url=base_url, max_retries=0)
        self._max_output_tokens = max_output_tokens
        self._default_timeout = default_timeout

    def _messages(self, capability: str, content: str) -> list[dict]:
        # O provider simulado reconhece a tarefa pela primeira linha "TASK: <nome>".
        # O nome lógico da capacidade é também o nome da tarefa, então reaproveitamos.
        return [{"role": "user", "content": f"TASK: {capability}\n{content}"}]

    def generate(self, capability: str, content: str, timeout: float | None = None) -> str:
        response = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=self._messages(capability, content),
            timeout=self._default_timeout if timeout is None else timeout,
        )
        return response.choices[0].message.content

    def stream(self, capability: str, content: str) -> Iterator[str]:
        # stream=True: o SDK devolve um iterador de chunks. Cada chunk traz um pedaço
        # do texto em `delta.content`. Os bytes começam a fluir no TTFT do provider,
        # bem antes de a geração terminar — é isso que permite o primeiro trecho cedo.
        # Uma falha no meio do stream (modo midstream_error do provider) levanta uma
        # exceção durante a iteração, que o chamador traduz no evento `error`.
        completion = self._client.chat.completions.create(
            model=capability,
            max_tokens=self._max_output_tokens,
            messages=self._messages(capability, content),
            timeout=self._default_timeout,
            stream=True,
        )
        for chunk in completion:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                yield piece
