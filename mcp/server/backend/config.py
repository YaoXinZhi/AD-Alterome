# -*- coding:utf-8 -*-
# ! usr/bin/env python3

import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args, **_kwargs):
        return False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MCP_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
PROJECT_DIR = os.path.abspath(os.path.join(MCP_DIR, ".."))

load_dotenv(os.path.join(MCP_DIR, ".env"))
load_dotenv(os.path.join(PROJECT_DIR, ".env"))


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(MCP_DIR, path))

# ----------------------------
# LLM config (保留给 demo_main.py 用)
# ----------------------------
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# ----------------------------
# Database
# ----------------------------
SQLITE_DB_PATH = os.getenv(
    "SQLITE_DB_PATH",
    os.path.join(PROJECT_DIR, "ADAlterome.db.sqlite3"),
)
SQLITE_DB_PATH = _resolve_path(SQLITE_DB_PATH)

CURATED_SQLITE_DB_PATH = os.getenv(
    "CURATED_SQLITE_DB_PATH",
    os.path.join(PROJECT_DIR, "data", "ad-alterome-db", "ad_alterome_curated.db"),
)
CURATED_SQLITE_DB_PATH = _resolve_path(CURATED_SQLITE_DB_PATH)

# ----------------------------
# Remote MCP server config
# ----------------------------
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "streamable-http")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8000"))
MCP_PATH = os.getenv("MCP_PATH", "/mcp")

# ----------------------------
# REST API config
# ----------------------------
ADALTEROME_API_BASE_URL = os.getenv(
    "ADALTEROME_API_BASE_URL",
    "http://127.0.0.1:8010",
).rstrip("/")
ADALTEROME_API_TIMEOUT = float(os.getenv("ADALTEROME_API_TIMEOUT", "180"))

# ----------------------------
# Security
# ----------------------------
MCP_API_KEY = os.getenv("MCP_API_KEY", "")
MCP_ALLOWED_ORIGINS = os.getenv("MCP_ALLOWED_ORIGINS", "")

# ----------------------------
# Logging
# ----------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
