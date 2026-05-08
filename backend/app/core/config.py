from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: str = "3306"
    MYSQL_DB: str = "fin_quant_db"

    ITICK_TOKEN: str = ""
    ITICK_HOST: str = "api0.itick.org"

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        return "sqlite:///fin_quant.db"

settings = Settings()