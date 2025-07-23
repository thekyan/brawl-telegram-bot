import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({"telegram_id": user.id})

    if not player:
        await update.message.reply_text("❌ Tu n'es pas encore inscrit. Utilise /register pour créer ton profil.")
        return

    msg = (
        f"👤 **Ton profil Brawl Stars**\n"
        f"• Pseudo : {player.get('username', 'Inconnu')}\n"
        f"• Trophées : {player.get('trophies', 'N/A')}\n"
        f"• Brawler principal : {player.get('main_brawler', 'N/A')}\n"
        f"• Victoires : {player.get('wins', 0)}\n"
        f"• Défaites : {player.get('defeats', 0)}\n"
        f"• Matchs joués : {player.get('matches_played', 0)}\n"
        f"• Inscrit le : {player.get('registered_at', datetime.utcnow()).strftime('%d/%m/%Y %H:%M')}\n"
    )

    if player.get("profile_photo"):
        await update.message.reply_photo(
            photo=player["profile_photo"],
            caption=msg
        )
    else:
        await update.message.reply_text(msg)