"""Client IA Lyvenia — remplace anthropic.Anthropic pour les builds client.

Proxifie les appels vers https://api.lyvenia.fr/ai/analyze et /ai/chat
en transmettant le JWT stocké localement.
"""
import requests

from core.auth_store import get_jwt

LYVENIA_API_URL = "https://api.lyvenia.fr"
_TIMEOUT = 180  # secondes — les analyses complètes peuvent prendre du temps


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
        except requests.exceptions.ConnectionError:
            raise ConnectionError(
                "Impossible de contacter le serveur Lyvenia. "
                "Vérifiez votre connexion internet."
            )
        except requests.exceptions.Timeout:
            raise TimeoutError(
                "Le serveur Lyvenia n'a pas répondu à temps. Réessayez."
            )

        if resp.status_code == 401:
            raise PermissionError(
                "Session expirée — veuillez vous reconnecter."
            )
        if resp.status_code == 429:
            raise RuntimeError(
                "Limite d'utilisation atteinte. Réessayez dans quelques instants."
            )
        if not resp.ok:
            err = resp.json().get("error", resp.text) if resp.content else resp.reason
            raise RuntimeError(f"Erreur serveur Lyvenia ({resp.status_code}) : {err}")

        data = resp.json()
        return _Message(data.get("content", ""))


class LyveniaAIClient:
    """Remplace anthropic.Anthropic(api_key=...) pour les builds client RODIA."""

    def __init__(self):
        self.messages = _Messages()
