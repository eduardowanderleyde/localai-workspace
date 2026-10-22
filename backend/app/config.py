from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuração lida de variáveis de ambiente (ou de um arquivo .env)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:8b"
    embedding_model: str = "bge-m3"
    # O Qwen3 tem modo de "raciocínio" (<think>); desligado por padrão para respostas mais rápidas.
    chat_think: bool = False
    request_timeout_s: float = 120.0

    system_prompt: str = (
        "Você é o Assistente da EMPETUR (Empresa de Turismo de Pernambuco), que roda localmente. "
        "Responda em português do Brasil, de forma objetiva e precisa. "
        "Se não souber a resposta, diga que não sabe em vez de inventar."
    )

    # Banco vazio desativa as rotas de documentos (útil em testes do chat).
    database_url: str = "postgresql://localai:localai@localhost:5434/localai"
    embedding_dim: int = 1024  # bge-m3

    chunk_size: int = 1200
    chunk_overlap: int = 200
    rag_top_k: int = 6
    # HyDE: trecho hipotético para ampliar a busca. Desligado: na avaliação não melhorou o hit@6.
    rag_hyde: bool = False
    # Similaridade de cosseno mínima para um trecho ser usado como fonte.
    rag_min_score: float = 0.45

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
