from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql://testpilot:testpilot@localhost:5432/testpilot"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    log_excerpt_chars: int = 12000
    similarity_candidates: int = 400
    max_tool_rounds: int = 3


def get_settings() -> Settings:
    return Settings()
