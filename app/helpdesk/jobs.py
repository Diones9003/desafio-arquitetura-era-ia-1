"""Armazém de tarefas assíncronas em memória (F3 — relatório de tópicos).

O relatório do mês inteiro cobre 5.000 tickets e leva minutos: não cabe numa resposta
síncrona sem estourar a paciência da borda (504). A feature vira Asynchronous
Request-Reply — o POST aceita o pedido, devolve `202` na hora e processa em segundo
plano; o cliente acompanha por uma URL de status e busca o resultado quando pronto.

Este módulo guarda o estado de cada tarefa. É um dicionário em memória, protegido por
um lock, porque o enunciado coloca "sobreviver a um reinício com tarefas em andamento"
explicitamente fora de escopo. Trocar isto por Redis/banco é mudança só deste módulo.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

State = Literal["pending", "running", "done", "failed"]


@dataclass
class Job:
    id: str
    state: State = "pending"
    processed: int = 0          # tickets já processados
    total: int = 0              # total de tickets do período
    reason: str | None = None   # motivo, quando state == "failed"
    result: dict | None = None  # relatório final, quando state == "done"
    start: date | None = None
    end: date | None = None

    @property
    def progress(self) -> str:
        return f"{self.processed}/{self.total}"


class JobStore:
    """Guarda e atualiza os jobs de forma segura entre threads."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, start: date, end: date) -> Job:
        job = Job(id=uuid.uuid4().hex[:8], start=start, end=end)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def set_running(self, job_id: str, total: int) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "running"
            job.total = total

    def set_progress(self, job_id: str, processed: int) -> None:
        with self._lock:
            self._jobs[job_id].processed = processed

    def set_done(self, job_id: str, result: dict) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "done"
            job.result = result

    def set_failed(self, job_id: str, reason: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "failed"
            job.reason = reason
