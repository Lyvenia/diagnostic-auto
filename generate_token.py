"""
Script admin — Génération d'une licence client DiagAuto.

Usage :
    1. Définir la variable d'environnement STRIPE_SECRET_KEY
       (dans un fichier .env ou directement dans le terminal)
    2. Créer manuellement un Prix récurrent sur Stripe Dashboard
       et copier son ID (price_XXXX) dans STRIPE_PRICE_ID ci-dessous
    3. Exécuter : python generate_token.py

Prérequis :
    pip install stripe python-dotenv

Le token généré est à copier dans le config.json du client :
    "licence_token": "<token>"
"""
import os
import sys
import uuid

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import stripe
except ImportError:
    print("❌  Module stripe manquant. Installez-le : pip install stripe")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
# ID du Prix Stripe récurrent (49€/mois) — à créer une fois dans le dashboard
# Stripe Dashboard → Products → Add product → 49,00 € / mois → copier price_XXXX
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "")

# ── Validation ────────────────────────────────────────────────────────────────

if not STRIPE_SECRET_KEY:
    print("❌  STRIPE_SECRET_KEY non définie.")
    print("    Définissez-la dans un fichier .env ou via :")
    print("    set STRIPE_SECRET_KEY=sk_live_...  (Windows)")
    print("    export STRIPE_SECRET_KEY=sk_live_... (macOS/Linux)")
    sys.exit(1)

if not STRIPE_PRICE_ID:
    print("❌  STRIPE_PRICE_ID non défini.")
    print("    Créez un prix récurrent sur Stripe Dashboard puis :")
    print("    set STRIPE_PRICE_ID=price_XXXXXXXXXXXX")
    sys.exit(1)

stripe.api_key = STRIPE_SECRET_KEY

# ── Informations client (optionnel) ──────────────────────────────────────────

print("=" * 55)
print("  🔑  Générateur de licence DiagAuto")
print("=" * 55)
print()

nom = input("Nom du client (Prénom Nom ou entreprise) : ").strip()
email = input("Email du client : ").strip()

# ── Génération du token UUID ──────────────────────────────────────────────────

licence_token = str(uuid.uuid4())

# ── Création du client Stripe ─────────────────────────────────────────────────

print()
print("  ⏳  Création du client Stripe...", end=" ", flush=True)

try:
    customer = stripe.Customer.create(
        name=nom if nom else None,
        email=email if email else None,
        metadata={"licence_token": licence_token},
    )
    print(f"✅  ({customer.id})")
except stripe.error.StripeError as e:
    print(f"❌  {e}")
    sys.exit(1)

# ── Création de l'abonnement Stripe (49€/mois) ────────────────────────────────

print("  ⏳  Création de l'abonnement 49€/mois...", end=" ", flush=True)

try:
    subscription = stripe.Subscription.create(
        customer=customer.id,
        items=[{"price": STRIPE_PRICE_ID}],
        collection_method="send_invoice",
        days_until_due=30,
        metadata={"licence_token": licence_token},
    )
    print(f"✅  ({subscription.id})")
except stripe.error.StripeError as e:
    print(f"❌  {e}")
    print("    Le client a été créé ({customer.id}) mais l'abonnement a échoué.")
    print("    Vous pouvez créer l'abonnement manuellement depuis le Dashboard Stripe.")
    sys.exit(1)

# ── Résultat ──────────────────────────────────────────────────────────────────

print()
print("=" * 55)
print("  ✅  Licence générée avec succès !")
print("=" * 55)
print()
print(f"  Client     : {nom or '(sans nom)'}")
print(f"  Email      : {email or '(sans email)'}")
print(f"  Stripe ID  : {customer.id}")
print(f"  Abonnement : {subscription.id} — {subscription.status}")
print()
print("  TOKEN À COPIER DANS config.json DU CLIENT :")
print()
print(f"    \"licence_token\": \"{licence_token}\"")
print()
print("=" * 55)
