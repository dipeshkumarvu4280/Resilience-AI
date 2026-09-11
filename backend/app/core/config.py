import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "RESILIENCE"
    PROJECT_DESCRIPTION: str = "AI-Powered Community Emergency Response & Resource Coordination Platform"
    API_V1_STR: str = "/api/v1"
    
    # Storage
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads")
    
    # Environment & Security
    SECRET_KEY: str = "resilience-emergency-response-cryptographic-salt-2026-key"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    OTP_EXPIRE_MINUTES: int = 5
    MAX_OTP_ATTEMPTS: int = 5
    
    # Database
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB_NAME: str = "resilience_db"
    LOCAL_MONGODB_URL: Optional[str] = "mongodb://localhost:27017"
    ATLAS_MONGODB_URL: Optional[str] = None
    
    # Geocoding
    GEOCODING_PROVIDER: str = "nominatim"
    GEOCODING_BASE_URL: str = "https://nominatim.openstreetmap.org/reverse"
    GEOCODING_USER_AGENT: str = "RESILIENCE-Emergency-Response-Platform/1.0 (contact@resilience.civil-defense.org)"
    GEOCODING_TIMEOUT_SECONDS: float = 5.0
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    
    # Google OAuth 2.0 / OpenID Connect
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/google/callback"
    GOOGLE_MAPS_API_KEY: Optional[str] = None
    VITE_GOOGLE_MAPS_API_KEY: Optional[str] = None
    ROUTING_TIMEOUT_SECONDS: float = 6.0
    
    # Phase 4: Situation Intelligence & Clustering
    SITUATION_CLUSTERING_DISTANCE_KM: float = 3.0  # Max distance to cluster compatible reports
    SITUATION_CLUSTERING_TIME_WINDOW_HOURS: float = 24.0  # Max temporal window for active clusters
    SITUATION_ASSESSMENT_TIMEOUT_SECONDS: float = 5.0
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FALLBACK_MODEL: Optional[str] = "gemini-1.5-flash"
    GEMINI_MAX_RETRIES: int = 3
    GEMINI_RETRY_BASE_DELAY_SECONDS: float = 0.5
    GEMINI_EXTRACTION_TIMEOUT_SECONDS: float = 6.0
    GEMINI_VISION_TIMEOUT_SECONDS: float = 10.0
    
    # Multi-Provider Multimodal Vision & Failover
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_VISION_MODEL: str = "gpt-4o"
    VISION_PRIMARY_PROVIDER: str = "GEMINI"
    VISION_FALLBACK_PROVIDER: str = "OPENAI"
    OPENAI_VISION_TIMEOUT_SECONDS: float = 12.0
    OPENAI_MAX_RETRIES: int = 2
    OPENAI_RETRY_BASE_DELAY_SECONDS: float = 0.5
    
    # Multi-Provider Text Extraction & Failover
    OPENAI_TEXT_MODEL: str = "gpt-5.6-luna"
    TEXT_PRIMARY_PROVIDER: str = "GEMINI"
    TEXT_FALLBACK_PROVIDER: str = "OPENAI"
    OPENAI_TEXT_TIMEOUT_SECONDS: float = 12.0
    
    # Phase 7: WhatsApp Provider & Messaging Configuration
    WHATSAPP_PROVIDER: str = "meta_cloud"  # "meta_cloud" or "mock"
    WHATSAPP_API_BASE_URL: str = "https://graph.facebook.com/v18.0"
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    
    # Phase 1: Live Web Push & VAPID Configuration (RFC 8291 / 8292)
    VAPID_PUBLIC_KEY: Optional[str] = None
    VAPID_PRIVATE_KEY: Optional[str] = None
    VAPID_CLAIMS_EMAIL: str = "mailto:emergency-alerts@resilience-civildefense.org"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
