import os
from pathlib import Path

# Cargar automáticamente variables desde un archivo .env si existe en la raíz o backend
def cargar_env_local():
    rutas_env = [
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env"
    ]
    for ruta in rutas_env:
        if ruta.exists():
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    linea = linea.strip()
                    if linea and not linea.startswith("#") and "=" in linea:
                        clave, valor = linea.split("=", 1)
                        os.environ.setdefault(clave.strip(), valor.strip())
            break

cargar_env_local()

class Settings:
    PROJECT_NAME: str = "GEORESCUE IA - Plataforma B2G & B2C"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"

    # Base de Datos PostgreSQL / PostGIS
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: str = os.getenv("DB_PORT", "5432")
    DB_NAME: str = os.getenv("DB_NAME", "db_quantum_georescue")
    DB_USER: str = os.getenv("DB_USER", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "omar123")

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:
        # Driver explícito: desde SQLAlchemy 2.1 "postgresql://" busca psycopg 3 y
        # requirements.txt instala psycopg2-binary.
        return f"postgresql+psycopg2://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Seguridad
    SECRET_KEY: str = os.getenv("SECRET_KEY", "quantum_secret_key_rescue_2026_super_secure")

    # API Geoespacial
    GEOAPIFY_API_KEY: str = os.getenv("GEOAPIFY_API_KEY", "d055c0b4-9aad-4446-b964-ffb91a31c15a")

    # Módulo antirrobo / correo institucional
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://localhost:3000")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME or "noreply@georescue.local")
    # Horas durante las que no se puede cambiar el correo de seguridad después de un
    # SOS, pánico o evidencia: quien tenga el dispositivo no puede desviar las fotos.
    SECURITY_EMAIL_LOCK_HOURS: int = int(os.getenv("SECURITY_EMAIL_LOCK_HOURS", "24"))

    # SMS firmado: los secretos se suministran exclusivamente por entorno.
    SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "console").lower()
    # Solo desarrollo: con SMS_PROVIDER=console, muestra en la terminal del backend el
    # texto que se habría enviado (por ejemplo el código OTP) para poder probar el
    # flujo completo sin proveedor. Nunca debe activarse en un servidor real.
    SMS_CONSOLE_PRINT_MESSAGES: bool = os.getenv("SMS_CONSOLE_PRINT_MESSAGES", "false").lower() in {"1", "true", "yes", "on"}
    SMS_SIGNATURE_HEADER: str = os.getenv("SMS_SIGNATURE_HEADER", "X-SMS-Signature")
    SMS_WEBHOOK_PUBLIC_URL: str = os.getenv("SMS_WEBHOOK_PUBLIC_URL", "")
    SMS_WEBHOOK_SECRET: str = os.getenv("SMS_WEBHOOK_SECRET", "")
    SMS_OTP_PEPPER: str = os.getenv("SMS_OTP_PEPPER", "")
    SMS_DEVICE_ENCRYPTION_KEY: str = os.getenv("SMS_DEVICE_ENCRYPTION_KEY", "")
    SMS_TIMESTAMP_WINDOW_SECONDS: int = int(os.getenv("SMS_TIMESTAMP_WINDOW_SECONDS", "86400"))
    SMS_OUTBOUND_LIMIT_COUNT: int = int(os.getenv("SMS_OUTBOUND_LIMIT_COUNT", "5"))
    SMS_OUTBOUND_LIMIT_WINDOW_SECONDS: int = int(os.getenv("SMS_OUTBOUND_LIMIT_WINDOW_SECONDS", "3600"))
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

    # Pagos / suscripciones
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_PRICE_ID_PRO: str = os.getenv("STRIPE_PRICE_ID_PRO", "price_pro_demo")
    STRIPE_PRICE_ID_ENTERPRISE: str = os.getenv("STRIPE_PRICE_ID_ENTERPRISE", "price_enterprise_demo")
    # "subscription" si los precios de Stripe son recurrentes (mensuales); "payment" si son de pago único.
    STRIPE_CHECKOUT_MODE: str = os.getenv("STRIPE_CHECKOUT_MODE", "subscription")

    # Datos que ve el usuario para pagar por fuera (Yape / Plin / transferencia).
    # Son valores de ejemplo: cámbialos en el archivo .env por los reales.
    PAYMENT_ACCOUNT_HOLDER: str = os.getenv("PAYMENT_ACCOUNT_HOLDER", "GEORESCUE IA (cuenta de ejemplo)")
    PAYMENT_YAPE_NUMBER: str = os.getenv("PAYMENT_YAPE_NUMBER", "999 999 999")
    PAYMENT_PLIN_NUMBER: str = os.getenv("PAYMENT_PLIN_NUMBER", "999 999 999")
    PAYMENT_BANK_ACCOUNT: str = os.getenv("PAYMENT_BANK_ACCOUNT", "BCP 000-0000000-0-00 (ejemplo)")
    DEFAULT_RESPONSE_INSTITUTION: str = os.getenv("DEFAULT_RESPONSE_INSTITUTION", "COER Cajamarca")

settings = Settings()
