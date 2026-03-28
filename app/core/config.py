from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "QuintetX"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    APP_ENV: str = "dev"
    AUTO_SEED_ON_STARTUP: bool = True

    # Server Settings
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 8000

    # Game Settings
    BOARD_SIZE: int = 40
    TIME_PER_MOVE: float = 0.5
    MOVE_TIMEOUT_SECONDS: int = 10

    # Database Settings
    MONGODB_URI: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "quintetx"
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 60000

    # Agent Heartbeat Settings
    HEARTBEAT_INTERVAL: float = 5.0
    HEARTBEAT_TIMEOUT: float = 15.0
    HEARTBEAT_CHECK_INTERVAL: float = 3.0

    # Security (Placeholders)
    SECRET_KEY: str = "change_this_to_a_secure_random_string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Seed admin account
    INITIAL_ADMIN_USERNAME: str = "admin"
    INITIAL_ADMIN_PASSWORD: str = "admin"
    INITIAL_ADMIN_EMAIL: str = "admin@quintetx.local"
    INITIAL_ADMIN_FULL_NAME: str = "System Admin"
    INITIAL_ADMIN_MSSV: str = "00000000"

    class Config:
        env_file = ".env"

settings = Settings()

