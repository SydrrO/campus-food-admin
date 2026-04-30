from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL_OVERRIDE: str | None = None

    # Database
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "campus_food"
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_TIMEOUT_SCAN_SECONDS: int = 30
    
    # WeChat
    WECHAT_PAY_MODE: str = "mock"
    WECHAT_APPID: str = ""
    WECHAT_SECRET: str = ""
    WECHAT_MCHID: str = ""
    WECHAT_API_KEY: str = ""
    WECHAT_API_V3_KEY: str = ""
    WECHAT_PAY_NOTIFY_URL: str = ""
    WECHAT_PAY_PRIVATE_KEY_PATH: str = ""
    WECHAT_PAY_PRIVATE_KEY: str = ""
    WECHAT_PAY_MERCHANT_SERIAL_NO: str = ""
    WECHAT_PAY_PLATFORM_CERT_PATH: str = ""
    WECHAT_PAY_PUBLIC_KEY_PATH: str = ""
    WECHAT_PAY_PUBLIC_KEY: str = ""
    WECHAT_PAY_PUBLIC_KEY_ID: str = ""
    WECHAT_PAY_TIMEOUT_MINUTES: int = 15
    
    # JWT
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24
    
    # App
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    UPLOADS_ROOT: str = ""
    UPLOADS_PUBLIC_PATH: str = "/uploads"
    
    @property
    def DATABASE_URL(self) -> str:
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}?charset=utf8mb4"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
