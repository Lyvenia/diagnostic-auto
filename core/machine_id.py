"""Génère un identifiant machine stable pour le verrouillage de licence."""
import hashlib
import socket
import uuid


def get_machine_id() -> str:
    """Retourne un hash SHA-256 stable basé sur l'adresse MAC + hostname.

    Stable à travers les redémarrages et les mises à jour de RODIA.
    Ne contient aucune donnée personnelle identifiable.
    """
    raw = f"{uuid.getnode()}:{socket.gethostname()}"
    return hashlib.sha256(raw.encode()).hexdigest()
