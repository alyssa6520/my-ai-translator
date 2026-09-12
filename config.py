import os
from dotenv import load_dotenv

load_dotenv(override=True)


class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

    SOURCE_LANGUAGE = os.getenv("SOURCE_LANGUAGE", "en")
    TARGET_LANGUAGE = os.getenv("TARGET_LANGUAGE", "zh-CN")

    DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    COURSES_DIR = os.path.join(DATA_DIR, "courses")
    AUDIO_DIR = os.path.join(DATA_DIR, "audio")

    CHUNK_SIZE = 1024
    SAMPLE_RATE = 44100
    RECORD_SECONDS = 5

    @classmethod
    def ensure_dirs(cls):
        for d in [cls.DATA_DIR, cls.COURSES_DIR, cls.AUDIO_DIR]:
            os.makedirs(d, exist_ok=True)


Config.ensure_dirs()
