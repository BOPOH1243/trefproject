from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    host_domain: str

    mail_username: str
    mail_password: str
    mail_from: str
    mail_port: int
    mail_server: str
    mail_tls: bool
    mail_ssl: bool
    template_folder: str

    db_user: str
    db_password: str
    db_host: str
    db_port: str
    db_name: str

    jwt_secret: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    email_confirmation_expire_minutes: int

    redis_host: str
    redis_port: int
    redis_db: int

    class Config:
        env_file = ".env"

    @property
    def computed_database_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

settings = Settings()
