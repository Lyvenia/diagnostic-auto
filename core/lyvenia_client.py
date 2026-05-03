"""Client IA Lyvenia — remplace anthropic.Anthropic pour les builds client.

Proxifie les appels vers https://api.lyvenia.fr/ai/analyze et /ai/chat
en transmettant le JWT stocké localement.
"""
import time as _t
import requests

from core.auth_store import get_jwt
from core.paths import LOG_PATH

LYVENIA_API_URL = "https://api.lyvenia.fr"
_TIMEOUT = 300  # secondes — analyses Claude Opus complètes (Lyvenia gunicorn = 300s)


def _log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{_t.strftime('%H:%M:%S')}] [Lyvenia] {msg}\n")
    except Exception:
        pass


class _ContentBlock:
    """Mimique anthropic.types.TextBlock."""
    __slots__ = ("text", "type")

    def __init__(self, text: str):
        self.text = text
        self.type = "text"


class _Message:
    """Mimique anthropic.types.Message."""
    __slots__ = ("content",)

    def __init__(self, text: str):
        self.content = [_ContentBlock(text)]


class _Messages:
    """Mimique client.messages"""

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list,
        system: str = "",
        **kwargs,
    ) -> _Message:
        token = get_jwt()
        if not token:
            raise PermissionError(
                "Non authentifié — veuillez vous connecter avec vos identifiants Lyvenia."
            )

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
            "system": system,
        }

        _log(f"POST /ai/analyze model={model} max_tokens={max_tokens} prompt_len={sum(len(m.get('content', '')) for m in messages)}")
        t0 = _t.time()

        try:
            resp = requests.post(
                f"{LYVENIA_API_URL}/ai/analyze",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=_TIMEOUT,
            )
        except requests.exceptions.ConnectionError as e:
            _log(f"ConnectionError après {_t.time()-t0:.1f}s : {e}")
            raise ConnectionError(
                "Impossible de contacter le serveur Lyvenia. "
                "Vérifiez votre connexion internet."
            )
        except requests.exceptions.Timeout as e:
            _log(f"Timeout après {_t.time()-t0:.1f}s : {e}")
            raise TimeoutError(
                "Le serveur Lyvenia n'a pas répondu à temps. Réessayez."
            )

        elapsed = _t.time() - t0
        _log(f"← HTTP {resp.status_code} en {elapsed:.1f}s (taille={len(resp.content)}o)")

        if resp.status_code == 401:
            raise PermissionError(
                "Session expirée — veuillez vous reconnecter."
            )
        if resp.status_code == 429:
            raise RuntimeError(
                "Limite d'utilisation atteinte. Réessayez dans quelques instants."
            )
        if not resp.ok:
            # La réponse peut être HTML (nginx 502/504) ou vide — on parse proprement
            try:
                err = resp.json().get("error", resp.text)
            except Exception:
                err = (resp.text[:200] if resp.text else None) or resp.reason or f"HTTP {resp.status_code}"
            _log(f"Erreur serveur : {err}")
            raise RuntimeError(f"Erreur serveur Lyvenia ({resp.status_code}) : {err}")

        try:
            data = resp.json()
        except Exception:
            _log(f"Réponse non-JSON : {resp.text[:200] if resp.text else '(vide)'}")
            raise RuntimeError(
                f"Réponse invalide du serveur Lyvenia (non-JSON). "
                f"Le service est peut-être en cours de redémarrage. "
                f"Réponse reçue : {resp.text[:100] if resp.text else '(vide)'}"
            )
        content_len = len(data.get("content", "") or "")
        _log(f"✓ Réponse OK — content={content_len} chars")
        return _Message(data.get("content", ""))


class LyveniaAIClient:
    """Remplace anthropic.Anthropic(api_key=...) pour les builds client RODIA."""

    def __init__(self):
        self.messages = _Messages()
