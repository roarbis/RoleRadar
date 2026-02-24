"""
AI provider abstraction for Job Hunter Australia.

Three providers, in recommended priority order:
  1. Ollama (local)         — free, private, requires local install
  2. Groq  (cloud)          — free tier (14,400 req/day), needs API key
  3. Gemini Flash (cloud)   — paid, highest quality — COST ATTACHED

All providers expose:
  generate(prompt, max_tokens) -> str
  is_available -> bool
  name: str
  is_premium: bool
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider names (used as keys throughout the app)
# ---------------------------------------------------------------------------
OLLAMA_NAME = "Ollama (local)"
GROQ_NAME = "Groq (free)"
GEMINI_NAME = "Gemini Flash (cost attached)"

SCORING_PROVIDERS = [OLLAMA_NAME, GROQ_NAME]
GENERATION_PROVIDERS = [GROQ_NAME, OLLAMA_NAME, GEMINI_NAME]

GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]
GEMINI_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash-exp",
]


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------
class AIProvider:
    name: str = "Unknown"
    is_premium: bool = False  # True → "(cost attached)"

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        raise NotImplementedError

    @property
    def is_available(self) -> bool:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ollama — local, free, private
# ---------------------------------------------------------------------------
class OllamaProvider(AIProvider):
    """
    Connects to a local Ollama server (default: http://localhost:11434).

    Setup:
      1. Download & install Ollama from https://ollama.com/download/windows
      2. In a terminal: ollama pull llama3.2
      3. Ollama auto-starts as a background service after installation.
    """

    name = OLLAMA_NAME
    is_premium = False

    RECOMMENDED_MODELS = ["llama3.2", "phi3", "llama3.1:8b", "mistral", "gemma2"]

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
    ):
        self.model = model.strip() or "llama3.2"
        self.base_url = base_url.rstrip("/")

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        import requests as _requests

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        try:
            resp = _requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except _requests.ConnectionError:
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}.\n"
                "Make sure Ollama is running. "
                "Install: https://ollama.com/download/windows  |  "
                f"Then run:  ollama pull {self.model}"
            )
        except _requests.HTTPError as e:
            if e.response.status_code == 404:
                raise RuntimeError(
                    f"Model '{self.model}' not found in Ollama.\n"
                    f"Run:  ollama pull {self.model}"
                )
            raise RuntimeError(f"Ollama HTTP error: {e}")
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}")

    @property
    def is_available(self) -> bool:
        """Returns True if Ollama is reachable at the configured URL."""
        import requests as _requests

        try:
            resp = _requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list:
        """Return list of model names currently downloaded in Ollama."""
        import requests as _requests

        try:
            resp = _requests.get(f"{self.base_url}/api/tags", timeout=3)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# Groq — cloud, free tier
# ---------------------------------------------------------------------------
class GroqProvider(AIProvider):
    """
    Uses Groq's cloud API — extremely fast, generous free tier.

    Free tier: ~14,400 requests/day for llama-3.1-8b-instant.
    API key: https://console.groq.com  (free sign-up)
    """

    name = GROQ_NAME
    is_premium = False

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.1-8b-instant",
    ):
        self.api_key = (api_key or "").strip()
        self.model = model or "llama-3.1-8b-instant"

    def generate(self, prompt: str, max_tokens: int = 800) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Groq API key not set. "
                "Get a free key at https://console.groq.com"
            )
        try:
            from groq import Groq

            client = Groq(api_key=self.api_key)
            completion = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.3,
            )
            return completion.choices[0].message.content.strip()
        except ImportError:
            raise ImportError(
                "groq package not installed.\n"
                "Run:  C:\\Temp\\ClaudeCode\\python313\\Scripts\\pip.exe install groq"
            )
        except Exception as e:
            raise RuntimeError(f"Groq error: {e}")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# Gemini Flash — premium (cost attached)
# ---------------------------------------------------------------------------
class GeminiProvider(AIProvider):
    """
    Google Gemini Flash — highest quality, but each call has a small cost.

    COST ATTACHED — use sparingly or for premium features only.
    API key: https://aistudio.google.com/app/apikey
    Pricing:  gemini-1.5-flash ~$0.075 / 1M input tokens (very cheap, but not free)
    """

    name = GEMINI_NAME
    is_premium = True  # "(cost attached)"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-flash",
    ):
        self.api_key = (api_key or "").strip()
        self.model = model or "gemini-1.5-flash"

    def generate(self, prompt: str, max_tokens: int = 1200) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Gemini API key not set. "
                "Get one free at https://aistudio.google.com/app/apikey"
            )
        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            model_obj = genai.GenerativeModel(self.model)
            response = model_obj.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": 0.4,
                },
            )
            return response.text.strip()
        except ImportError:
            raise ImportError(
                "google-generativeai package not installed.\n"
                "Run:  C:\\Temp\\ClaudeCode\\python313\\Scripts\\pip.exe install google-generativeai"
            )
        except Exception as e:
            raise RuntimeError(f"Gemini error: {e}")

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_provider(
    provider_name: str,
    ollama_url: str = "http://localhost:11434",
    ollama_model: str = "llama3.2",
    groq_key: str = "",
    groq_model: str = "llama-3.1-8b-instant",
    gemini_key: str = "",
    gemini_model: str = "gemini-1.5-flash",
) -> AIProvider:
    """
    Build and return an AIProvider instance by display name.

    Args:
        provider_name: One of OLLAMA_NAME, GROQ_NAME, GEMINI_NAME.
        ... credential/model kwargs for the selected provider.

    Returns:
        Configured AIProvider instance.

    Raises:
        ValueError: Unknown provider name.
    """
    if provider_name == OLLAMA_NAME:
        return OllamaProvider(model=ollama_model, base_url=ollama_url)
    elif provider_name == GROQ_NAME:
        return GroqProvider(api_key=groq_key, model=groq_model)
    elif provider_name == GEMINI_NAME:
        return GeminiProvider(api_key=gemini_key, model=gemini_model)
    else:
        raise ValueError(f"Unknown AI provider: '{provider_name}'")
