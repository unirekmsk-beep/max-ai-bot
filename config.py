import os

# === НАСТРОЙКИ БОТА ===
MAX_BOT_TOKEN = os.environ.get("MAX_BOT_TOKEN", "")

# === НАСТРОЙКИ API ===
PROXYAPI_KEY = "sk-hNVh76Qv2H3Z3ByTLB0kYNhpg2NEotg5"
PROXYAPI_BASE = "https://api.proxyapi.ru/openai/v1"

# DeepSeek API
DEEPSEEK_API_KEY = "sk-15e4d936eb764f0d86add9e96fc0f665"
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"

# === ЮKassa ===
YOOKASSA_SHOP_ID = os.environ.get("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.environ.get("YOOKASSA_SECRET_KEY", "")

# Система бесплатных запросов
FREE_REQUESTS_SYSTEM = {
    "daily_free": 10,
    "registration_bonus": 20,
    "free_models": ["deepseek-chat"]
}

# МОДЕЛИ С ЦЕНАМИ В РУБЛЯХ
MODELS = {
    "deepseek-chat": {
        "name": "DeepSeek 🐉",
        "price": 0,
        "premium": False,
        "description": "Умная китайская модель, отлично программирует",
        "api_type": "deepseek",
        "model_name": "deepseek-chat"
    },
    "gpt-4o": {
        "name": "GPT-4o 🔷",
        "price": 50,
        "premium": True,
        "description": "Новейшая модель OpenAI, самая умная",
        "api_type": "proxyapi",
        "model_name": "gpt-4o"
    },
    "gpt-4": {
        "name": "GPT-4 🔶",
        "price": 70,
        "premium": True,
        "description": "Мощная модель OpenAI, отличные ответы",
        "api_type": "proxyapi",
        "model_name": "gpt-4"
    },
    "gpt-3.5-turbo": {
        "name": "GPT-3.5 Turbo 💨",
        "price": 20,
        "premium": True,
        "description": "Быстрая и недорогая модель OpenAI",
        "api_type": "proxyapi",
        "model_name": "gpt-3.5-turbo"
    }
}
