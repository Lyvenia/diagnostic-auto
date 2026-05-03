"""Signal d'arrêt propre — partagé entre update_routes et main."""
import threading

# Mis à True par update_routes quand la mise à jour est prête.
# _watch_heartbeat le détecte et retourne → main() peut nettoyer puis os._exit.
event = threading.Event()
