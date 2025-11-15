from typing import Optional
from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    DATABASE_URI: Optional[PostgresDsn] = None

    @field_validator("DATABASE_URI", mode="before")
    @classmethod
    def validate_database_uri(cls, v: Optional[str]) -> Optional[str]:
        # Если DATABASE_URI уже задан, возвращаем как есть
        if isinstance(v, str) and v:
            return v
        return None

    @model_validator(mode="after")
    def assemble_db_connection(self) -> "Settings":
        # Если DATABASE_URI не задан, собираем из отдельных полей
        if not self.DATABASE_URI:
            try:
                from urllib.parse import quote_plus
                # Экранируем специальные символы в пароле и других полях
                user = quote_plus(self.POSTGRES_USER)
                password = quote_plus(self.POSTGRES_PASSWORD)
                host = self.POSTGRES_HOST
                db = self.POSTGRES_DB
                
                # Собираем URI вручную
                database_uri = f"postgresql://{user}:{password}@{host}/{db}"
                self.DATABASE_URI = PostgresDsn(database_uri)
            except Exception:
                # Если не удалось собрать URI, оставляем None
                pass
        return self

    DOCKER_MODE: bool
    LOGGING_LEVEL: str

    SCHEDULE_URL: str = "https://misis.ru/students/schedule/"
    
    # Root path for reverse proxy (Traefik, nginx, etc.)
    ROOT_PATH: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        # Переменные окружения имеют приоритет над .env файлом
        env_file_encoding="utf-8",
    )


settings = Settings()
