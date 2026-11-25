"""Portas (contratos) do domínio helpdesk.

A aplicação depende apenas desta abstração para falar com o modelo de linguagem.
Qualquer implementação concreta (gateway, mock de teste, outro provedor) só precisa
satisfazer o protocolo `LLMPort`. É aqui que o acoplamento entre as features e a
infraestrutura de LLM é quebrado: as features importam a porta, nunca um SDK.
"""

from typing import Iterator, Protocol


class LLMPort(Protocol):
    """Contrato mínimo para gerar texto a partir de uma capacidade lógica.

    `capability` é o nome lógico da tarefa (ex.: "classify", "suggest", "topics",
    "extract"). O adaptador concreto decide qual modelo físico atende cada
    capacidade — as features não sabem nem se importam com isso.
    """

    def generate(self, capability: str, content: str, timeout: float | None = None) -> str:
        """Gera a resposta textual completa (síncrona) para a capacidade e o conteúdo.

        `timeout` é o teto explícito de tempo da chamada, em segundos. Ao estourar,
        a implementação levanta erro — nenhuma feature síncrona fica pendurada.
        """
        ...

    def stream(self, capability: str, content: str) -> Iterator[str]:
        """Gera a resposta em pedaços (streaming), um trecho de texto por vez.

        Usada pela feature cujo contrato é consumível aos poucos (F2). A primeira
        parte do texto chega cedo; o restante segue chegando até terminar. Se o
        provider interromper no meio, a iteração levanta erro — o chamador converte
        isso no evento `error` do stream.
        """
        ...
