import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les infos et captures des derniers matchs joués"""
    # On récupère les 10 derniers matchs terminés
    matches = db.matches.find({"status": {"$in": ["ready", "finished"]}}).sort("created_at", -1).limit(10)
    found = False
    async for match in matches:
        found = True
        msg = (
            f"🎮 Match {match.get('mode', '')}\n"
            f"• Joueur 1 : {match.get('username', 'Inconnu')}\n"
            f"• Joueur 2 : {match.get('opponent_username', 'Inconnu')}\n"
            f"• Date : {match.get('created_at', datetime.utcnow()).strftime('%d/%m/%Y %H:%M')}\n"
            f"• Statut : {match.get('status', 'inconnu')}\n"
        )
        # Cherche une capture liée à ce match (par joueur et date proche)
        screenshot = db.match_screens.find_one({
            "timestamp": {"$gte": match.get("created_at", datetime.utcnow())},
            "$or": [
                {"telegram_id": match.get("telegram_id")},
                {"telegram_id": match.get("opponent_id")}
            ]
        })
        if screenshot and screenshot.get("photo_url"):
            await update.message.reply_photo(
                photo=screenshot["photo_url"],
                caption=msg
            )
        else:
            await update.message.reply_text(msg)
    if not found:
        await update.message.reply_text("Aucun match n'a encore eu lieu.")