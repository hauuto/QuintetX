from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "QuintetX"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Game Settings
    BOARD_SIZE: int = 40
    TIME_PER_MOVE: float = 0.5

    # Database Settings
    DB_NAME: str = "quintetx"
    # MONGODB_URI: str = "mongodb://localhost:27017" # Uncomment when DB is ready

    # Security (Placeholders)
    SECRET_KEY: str = "change_this_to_a_secure_random_string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Heartbeat Settings
    HEARTBEAT_INTERVAL: float = 5.0
    HEARTBEAT_TIMEOUT: float = 15.0
    HEARTBEAT_CHECK_INTERVAL: float = 3.0

    class Config:
        env_file = ".env"

settings = Settings()

