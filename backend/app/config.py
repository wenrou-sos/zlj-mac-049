from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 为空时使用 SQLite,开箱即用;生产环境可在 .env 中配置 PostgreSQL:
    # postgresql+psycopg2://user:pass@host:5432/dbname
    database_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        # 由 database.py 基于 backend 目录解析绝对路径
        from .database import _DEFAULT_SQLITE_URL

        return _DEFAULT_SQLITE_URL

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
