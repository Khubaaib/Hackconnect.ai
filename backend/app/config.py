from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    environment: str = 'development'
    database_url: str = ''
    supabase_url: str = ''
    supabase_anon_key: str = ''
    supabase_service_role_key: str = ''
    cors_origins: str = 'http://localhost:3000'
    xai_api_key: str = ''
    xai_model: str = ''
    ai_daily_requests: int = 20
    ai_platform_daily_requests: int = 200
    telegram_webhook_secret: str = ''
    telegram_channel_id: str = ''
    telegram_api_id: int = 0
    telegram_api_hash: str = ''
    telegram_session_string: str = ''
    telegram_sync_interval_seconds: int = 60
    job_secret: str = ''
    verification_max_age_days: int = 14
    max_import_rows: int = 1000
    def validate_production(self):
        if self.environment == 'production':
            for field in ('database_url','supabase_url','supabase_anon_key','supabase_service_role_key','job_secret'):
                if not getattr(self,field): raise RuntimeError(f'Missing required configuration: {field}')
            if '*' in self.cors_origins or any(not s.strip().startswith('https://') for s in self.cors_origins.split(',')):
                raise RuntimeError('Production CORS origins must be explicit HTTPS origins')
@lru_cache
def settings(): return Settings()

