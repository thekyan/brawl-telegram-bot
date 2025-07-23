import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

async def findall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    players = db.players.find().sort("registered_at", -1)
    found = False
    for player in players:
        found = True
        msg = (
            f"👤 Pseudo : {player.get('username', 'Inconnu')}\n"
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
    if not found:
        await update.message.reply_text("Aucun joueur inscrit pour le moment.")