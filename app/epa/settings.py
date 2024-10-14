"""
Django settings for EPA project.

Generated by 'django-admin startproject' using Django 3.0.

For more information on this file, see
https://docs.djangoproject.com/en/3.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.0/ref/settings/
"""
import ast
import os

from django.contrib.messages import constants as messages

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = ast.literal_eval(os.getenv("DEBUG", "False"))

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.0/howto/static-files/
STATICFILES_DIRS = (os.path.join(BASE_DIR, "static"),)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "cdn_static_root")

STATICFILES_FINDERS = ["django.contrib.staticfiles.finders.FileSystemFinder"]

if DEBUG is True:
    STATICFILES_FINDERS.append("sass_processor.finders.CssFinder")
    SASS_PROCESSOR_ROOT = STATIC_ROOT
    SASS_PRECISION = 8
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("EPA_SECRET_KEY", "v@p9^=@lc3#1u_xtx*^xhrv0l3li1(+8ik^k@g-_bzmexb0$7n")

ALLOWED_HOSTS = ["*"]

CSRF_TRUSTED_ORIGINS = [
    f"https://{os.getenv('TRUSTED_HOST')}",
    f"http://{os.getenv('TRUSTED_HOST')}",
]
# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.forms",
    "users.apps.UsersConfig",
    "projects.apps.ProjectsConfig",
    "dashboard.apps.DashboardConfig",
    "cp_nigeria.apps.CPNigeriaConfig",
    "business_model.apps.BusinessModelConfig",
    # 3rd Party
    "crispy_forms",
    "django_q",
]

if DEBUG is True:
    INSTALLED_APPS.append("sass_processor")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]

ROOT_URLCONF = "epa.urls"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [os.path.join(BASE_DIR, "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "epa.context_processors.debug",
            ]
        },
    }
]

WSGI_APPLICATION = "epa.wsgi.application"

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases
# SQLite is used if no other database system is set via environment variables.
DATABASES = {
    "default": {
        "ENGINE": os.environ.get("SQL_ENGINE"),
        "NAME": os.environ.get("SQL_DATABASE"),
        "USER": os.environ.get("SQL_USER"),
        "PASSWORD": os.environ.get("SQL_PASSWORD"),
        "HOST": os.environ.get("SQL_HOST"),
        "PORT": os.environ.get("SQL_PORT"),
    }
    if os.environ.get("SQL_ENGINE")
    else {
        "ENGINE": os.environ.get("SQL_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("SQL_DATABASE", os.path.join(BASE_DIR, "db.sqlite3")),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = "en"

LOCALE_PATHS = (os.path.join(BASE_DIR, "locale"),)

LANGUAGES = [("en", "English")]

TIME_ZONE = "Europe/Copenhagen"

USE_I18N = True

USE_L10N = True

USE_TZ = False

# Other configs

AUTH_USER_MODEL = "users.CustomUser"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home_cpn"
LOGOUT_REDIRECT_URL = "home_cpn"

CRISPY_TEMPLATE_PACK = "bootstrap4"

# Please note, we don't use Django's internal email system,
# we implement our own, using exchangelib
USE_EXCHANGE_EMAIL_BACKEND = ast.literal_eval(os.getenv("USE_EXCHANGE_EMAIL_BACKEND", "True"))
# The Exchange account which sends emails
EXCHANGE_ACCOUNT = os.getenv("EXCHANGE_ACCOUNT", "dummy@dummy.com")
EXCHANGE_PW = os.getenv("EXCHANGE_PW", "dummypw")
EXCHANGE_EMAIL = os.getenv("EXCHANGE_EMAIL", "dummy@dummy.com")
EXCHANGE_SERVER = os.getenv("EXCHANGE_SERVER", "dummy.com")
# Email addresses to which feedback emails will be sent
RECIPIENTS = os.getenv("RECIPIENTS", "dummy@dummy.com,dummy2@dummy.com").split(",")
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[open_plan] ")

MESSAGE_TAGS = {
    messages.DEBUG: "alert-info",
    messages.INFO: "alert-info",
    messages.SUCCESS: "alert-success",
    messages.WARNING: "alert-warning",
    messages.ERROR: "alert-danger",
}

USE_PROXY = ast.literal_eval(os.getenv("USE_PROXY", "True"))
PROXY_ADDRESS_LINK = os.getenv("PROXY_ADDRESS", "http://proxy:port")
PROXY_CONFIG = ({"http://": PROXY_ADDRESS_LINK, "https://": PROXY_ADDRESS_LINK}) if USE_PROXY else ({})

MVS_API_HOST = os.getenv("MVS_API_HOST", "https://mvs-eland.rl-institut.de")
MVS_POST_URL = f"{MVS_API_HOST}/sendjson/"
MVS_GET_URL = f"{MVS_API_HOST}/check/"
MVS_LP_FILE_URL = f"{MVS_API_HOST}/get_lp_file/"
MVS_SA_POST_URL = f"{MVS_API_HOST}/sendjson/openplan/sensitivity-analysis"
MVS_SA_GET_URL = f"{MVS_API_HOST}/check-sensitivity-analysis/"

# Allow iframes to show in page
X_FRAME_OPTIONS = "SAMEORIGIN"

# API token to fetch exchange rates
EXCHANGE_RATES_API_TOKEN = os.getenv("EXCHANGE_RATES_API_TOKEN")
EXCHANGE_RATES_URL = f"https://v6.exchangerate-api.com/v6/{EXCHANGE_RATES_API_TOKEN}/latest/USD"

import sys

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "dtlnm": {
            "format": "%(asctime)s - %(levelname)8s - %(name)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }
    },
    "handlers": {
        "info_file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "django_epa_info.log",
            "formatter": "dtlnm",
        },
        "warnings_file": {
            "level": "WARNING",
            "class": "logging.FileHandler",
            "filename": "django_epa_warning.log",
            "formatter": "dtlnm",
        },
        "console": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
        },
    },
    "loggers": {
        "": {
            "handlers": ["info_file", "warnings_file", "console"],
            "level": "DEBUG",
            "propagate": True,
        },
        "asyncio": {"level": "WARNING"},
    },
}

# DJANGO-Q CONFIGURATION
# source: https://django-q.readthedocs.io/en/latest/configure.html
Q_CLUSTER = {
    "name": "django_q_orm",
    "workers": 4,
    "timeout": 90,
    "retry": 120,
    "queue_limit": 50,
    "orm": "default",
}
