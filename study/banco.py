from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

class BancoProgresso:
    def __init__(self, caminho: str | Path):
        alvo = Path(caminho)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        self.caminho = alvo
        self.conexao = sqlite3.connect(alvo, check_same_thread=False)
        self.cursor = self.conexao.cursor()
        self._criar_tabelas()

    def _criar_tabelas(self) -> None:
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_number INTEGER NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_number)
            )
            """
        )
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS question_edits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_number INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(question_number, field_name)
            )
            """
        )
        self.conexao.commit()

    def carregar_respostas(self) -> dict[int, dict]:
        self.cursor.execute(
            "SELECT question_number, user_answer, is_correct FROM user_responses"
        )
        return {
            numero: {"resposta": resposta, "correta": bool(correta)}
            for numero, resposta, correta in self.cursor.fetchall()
        }

    def salvar_resposta(self, numero: int, resposta: str, correta: bool) -> None:
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO user_responses
                (question_number, user_answer, is_correct, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (numero, resposta, int(correta), datetime.now()),
        )
        self.conexao.commit()

    def limpar_respostas(self) -> int:
        self.cursor.execute("SELECT COUNT(*) FROM user_responses")
        total = self.cursor.fetchone()[0]
        self.cursor.execute("DELETE FROM user_responses")
        self.conexao.commit()
        return total

    def estatisticas(self) -> tuple[int, int]:
        self.cursor.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END), 0)
            FROM user_responses
            """
        )
        respondidas, acertos = self.cursor.fetchone()
        return int(respondidas or 0), int(acertos or 0)

    def carregar_edicoes(self) -> dict[int, dict[str, str]]:
        self.cursor.execute(
            "SELECT question_number, field_name, new_value FROM question_edits"
        )
        edicoes: dict[int, dict[str, str]] = {}
        for numero, campo, valor in self.cursor.fetchall():
            edicoes.setdefault(numero, {})[campo] = valor
        return edicoes

    def salvar_edicao(self, numero: int, campo: str, antigo: str, novo: str) -> None:
        self.cursor.execute(
            """
            INSERT OR REPLACE INTO question_edits
                (question_number, field_name, old_value, new_value, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (numero, campo, antigo, novo, datetime.now()),
        )
        self.conexao.commit()

    def fechar(self) -> None:
        try:
            self.conexao.close()
        except Exception:
            pass
