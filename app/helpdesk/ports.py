"""Portas (contratos) do domínio helpdesk.

A aplicação depende apenas desta abstração para falar com o modelo de linguagem.
Qualquer implementação concreta (gateway, mock de teste, outro provedor) só precisa
satisfazer o protocolo `LLMPort`. É aqui que o acoplamento entre as features e a
infraestrutura de LLM é quebrado: as features importam a porta, nunca um SDK.
"""

from typing import Protocol


class LLMPort(Protocol):
    """Contrato mínimo para gerar texto a partir de uma capacidade lógica.

    `capability` é o nome lógico da tarefa (ex.: "classify", "suggest", "topics",
    "extract"). O adaptador concreto decide qual modelo físico atende cada
    capacidade — as features não sabem nem se importam com isso.
    """

    def generate(self, capability: str, content: str) -> str:
        """Gera a resposta textual do modelo para a capacidade e o conteúdo dados."""
        ...
