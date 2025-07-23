import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client.brawlbase

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({'telegram_id': user.id})

    if player:
        await update.message.reply_text(
            f"👋 Salut {user.first_name} ! Ravi de te revoir sur le Brawl Stars Tournament Bot ! 🏆"
        )
    else:
        await update.message.reply_text(
            f"👋 Salut {user.first_name} ! Bienvenue sur le Brawl Stars Tournament Bot ! 🏆\n"
            "Tu n'es pas encore enregistré.\n"
            "Envoie la commande /register <trophées> [brawler_principal] pour créer ton profil.\n"
            "Exemple : /register 150 Shelly"
        )