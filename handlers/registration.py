# handlers/registration.py
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import logging
from pymongo import MongoClient
from typing import Optional

# Configuration du logger
logger = logging.getLogger(__name__)

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Gère la commande /register pour enregistrer ou mettre à jour un joueur
    Usage: /register <trophées> [brawler_principal]
    """
    try:
        user = update.effective_user
        
        # Validation des arguments
        if not context.args or len(context.args) < 1:
            await update.message.reply_text(
                "ℹ️ Usage: /register <trophées> [brawler_principal]\n"
                "Exemple: /register 150 Shelly"
            )
            return

        try:
            trophies = int(context.args[0])
            if trophies < 0 or trophies > 50000:  # Plage réaliste
                raise ValueError
        except ValueError:
            await update.message.reply_text("❌ Le nombre de trophées doit être entre 0 et 50 000")
            return

        # Brawler optionnel (valeur par défaut 'Unknown')
        main_brawler = context.args[1] if len(context.args) > 1 else "Unknown"

        # Données du joueur
        player_data = {
            "telegram_id": user.id,
            "username": user.username or "Anonyme",
            "trophies": trophies,
            "main_brawler": main_brawler,
            "registered_at": datetime.utcnow(),
            "last_active": datetime.utcnow(),
            "matches_played": 0,
            "wins": 0
        }

        # Opération atomique
        db.players.update_one(
            {"telegram_id": user.id},
            {"$set": player_data},
            upsert=True
        )

        await update.message.reply_text(
            f"🎉 Profil enregistré !\n"
            f"• Trophées: {trophies}\n"
            f"• Brawler principal: {main_brawler}\n"
            f"Utilisez /findmatch pour commencer !"
        )

    except Exception as e:
        logger.error(f"Erreur d'enregistrement pour {user.id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Une erreur critique est survenue. Contactez l'administrateur."
        )

def setup(application):
    application.add_handler(CommandHandler("register", register))