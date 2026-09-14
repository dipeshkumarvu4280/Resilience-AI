import os
from typing import List, Optional, Union
from pydantic import field_validator
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
    OTP_RESEND_COOLDOWN_SECONDS: int = 30
    
    # Prototype / Demo Verification Mode
    # WARNING: Simulated OTP is strictly for prototype/demo environments.
    # When enabled, no real SMS/Email/WhatsApp dispatch occurs; OTP is surfaced directly in the prototype response.
    # NEVER enable SIMULATED_OTP_MODE in production without explicit authorized requirement.
    SIMULATED_OTP_MODE: bool = True
    
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
    
    # Frontend Public URL
    FRONTEND_BASE_URL: str = "https://resilience-ai-pied.vercel.app"
    
    # CORS
    BACKEND_CORS_ORIGINS: Union[List[str], str] = [
        "https://resilience-ai-pied.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
    CORS_ALLOWED_ORIGINS: Optional[Union[List[str], str]] = None

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str], None]) -> List[str]:
        if not v:
            return [
                "https://resilience-ai-pied.vercel.app",
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:3000",
            ]
        if isinstance(v, str):
            v_stripped = v.strip()
            if v_stripped.startswith("[") and v_stripped.endswith("]"):
                import json
                try:
                    parsed = json.loads(v_stripped)
                    if isinstance(parsed, list):
                        return [str(item).strip().rstrip("/") for item in parsed if item]
                except Exception:
                    pass
            return [item.strip().rstrip("/") for item in v.split(",") if item.strip()]
        if isinstance(v, list):
            return [str(item).strip().rstrip("/") for item in v if item]
        return v

    @property
    def cors_origins(self) -> List[str]:
        origins: List[str] = []
        if isinstance(self.BACKEND_CORS_ORIGINS, list):
            for orig in self.BACKEND_CORS_ORIGINS:
                clean = str(orig).strip().rstrip("/")
                if clean and clean not in origins:
                    origins.append(clean)
        elif isinstance(self.BACKEND_CORS_ORIGINS, str):
            for orig in self.BACKEND_CORS_ORIGINS.split(","):
                clean = orig.strip().rstrip("/")
                if clean and clean not in origins:
                    origins.append(clean)
        
        if self.CORS_ALLOWED_ORIGINS:
            if isinstance(self.CORS_ALLOWED_ORIGINS, list):
                for orig in self.CORS_ALLOWED_ORIGINS:
                    clean = str(orig).strip().rstrip("/")
                    if clean and clean not in origins:
                        origins.append(clean)
            elif isinstance(self.CORS_ALLOWED_ORIGINS, str):
                s = self.CORS_ALLOWED_ORIGINS.strip()
                if s.startswith("[") and s.endswith("]"):
                    import json
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, list):
                            for orig in parsed:
                                clean = str(orig).strip().rstrip("/")
                                if clean and clean not in origins:
                                    origins.append(clean)
                    except Exception:
                        pass
                for orig in self.CORS_ALLOWED_ORIGINS.split(","):
                    clean = orig.strip().rstrip("/")
                    if clean and clean not in origins:
                        origins.append(clean)
        
        default_origins = [
            "https://resilience-ai-pied.vercel.app",
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
        for default_orig in default_origins:
            if default_orig not in origins:
                origins.append(default_orig)
        return origins
    
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
    
    # Phase 7: WhatsApp Provider & Messaging Configuration (Meta Cloud & Twilio Sandbox)
    WHATSAPP_PROVIDER: str = "meta_cloud"  # "meta_cloud", "meta", "twilio", "mock", or "disabled"
    WHATSAPP_API_BASE_URL: str = "https://graph.facebook.com/v18.0"
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_BUSINESS_ACCOUNT_ID: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v18.0"

    # Twilio WhatsApp Sandbox Configuration
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    TWILIO_WHATSAPP_ENABLED: bool = True
    TWILIO_WHATSAPP_STATUS_CALLBACK_URL: Optional[str] = None
    TWILIO_VALIDATE_SIGNATURE: bool = True

    # Twilio SMS Configuration
    SMS_PROVIDER: str = "disabled"  # "twilio", "mock", or "disabled"
    TWILIO_SMS_ENABLED: bool = False
    TWILIO_SMS_FROM: Optional[str] = None
    TWILIO_SMS_STATUS_CALLBACK_URL: Optional[str] = None
    TWILIO_SMS_MODE: str = "trial_template"  # "trial_template" or "custom"
    TWILIO_SMS_TRIAL_TEMPLATE: str = "sms_internal_alerts"  # Predefined Twilio trial template: sms_internal_alerts / sms_account_alerts

    @property
    def whatsapp_verify_token(self) -> str:
        return (self.WHATSAPP_VERIFY_TOKEN or self.WHATSAPP_WEBHOOK_VERIFY_TOKEN or "").strip()
    
    # Phase 1: Live Web Push & VAPID Configuration (RFC 8291 / 8292)
    WEB_PUSH_ENABLED: bool = True
    VAPID_PUBLIC_KEY: Optional[str] = "BCo18wf1RGpeXAmItEw2vjvHGeT09MOzsTD4xN0iD6D8bt6jk3CwWvSv7yVNKr14TkwljYpK5Usrqu1opS0mUQw"
    VAPID_PRIVATE_KEY: Optional[str] = "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgk73HvjnRn5q6WmUX\nkAh6WWpAGsqyCh5ffJ0rTGfiDYehRANCAAQqNfMH9URqXlwJiLRMNr47xxnk9PTD\ns7Ew+MTdIg+g/G7eo5NwsFr0r+8lTSq9eE5MJY2KSuVLK6rtaKUtJlEM\n-----END PRIVATE KEY-----\n"
    VAPID_CLAIMS_EMAIL: str = "mailto:emergency-alerts@resilience-civildefense.org"
    
    # Real Weather Intelligence Provider
    WEATHER_PROVIDER: str = "open_meteo"  # "open_meteo", "google", "disabled"
    WEATHER_API_KEY: Optional[str] = None
    WEATHER_TIMEOUT_SECONDS: float = 4.0
    WEATHER_CACHE_TTL_SECONDS: int = 600
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
