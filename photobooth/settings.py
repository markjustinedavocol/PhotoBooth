"""Settings for the Miles Apart photobooth."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render sets this automatically (e.g. miles-apart.onrender.com).
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Render terminates HTTPS in front of the app and forwards the original scheme.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "couples",
    "booth",
    "gallery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.UserTimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "photobooth.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "couples.context_processors.couple",
            ],
        },
    },
]

WSGI_APPLICATION = "photobooth.wsgi.application"
ASGI_APPLICATION = "photobooth.asgi.application"

# SQLite by default; set DATABASE_URL (e.g. postgres://user:pass@host:5432/db) for PostgreSQL.
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Real-time booth sync. Redis in production, in-memory for local development.
REDIS_URL = env("REDIS_URL", default="")
if REDIS_URL:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded photos are private: there is deliberately no MEDIA_URL route.
# Every image is served through a view that checks the viewer belongs to the couple.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

# With CLOUDINARY_URL set (cloudinary://key:secret@cloud_name) photos go to
# Cloudinary as private files; otherwise they're stored on disk in MEDIA_ROOT.
# Render's disk is wiped on every deploy, so production needs Cloudinary.
CLOUDINARY_URL = env("CLOUDINARY_URL", default="")
CLOUDINARY_FOLDER = env("CLOUDINARY_FOLDER", default="miles-apart")
STORAGES = {
    "default": {
        "BACKEND": (
            "photobooth.storage.PrivateCloudinaryStorage"
            if CLOUDINARY_URL
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "couples:dashboard"
LOGOUT_REDIRECT_URL = "home"

# Password-reset emails print to the log unless EMAIL_URL is set,
# e.g. smtp+tls://you@gmail.com:app-password@smtp.gmail.com:587
if env("EMAIL_URL", default=""):
    vars().update(env.email_url("EMAIL_URL"))
else:
    EMAIL_BACKEND = env(
        "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
    )
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="Miles Apart <hello@milesapart.local>")

# Upload limits (bytes)
MAX_FRAME_UPLOAD_SIZE = 6 * 1024 * 1024
MAX_AVATAR_UPLOAD_SIZE = 3 * 1024 * 1024

if not DEBUG:
    SESSION_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
    CSRF_COOKIE_SECURE = env.bool("SECURE_COOKIES", default=True)
