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
        msg = (
            f"👋 Salut {player.get('username', user.first_name)} ! Ravi de te revoir sur le Brawl Stars Tournament Bot ! 🏆"
        )
        # Affiche la photo si elle existe
        if player.get("profile_photo"):
            await update.message.reply_photo(
                photo=player["profile_photo"],
                caption=msg
            )
        else:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text(
            f"👋 Salut {user.first_name} ! Bienvenue sur le Brawl Stars Tournament Bot ! 🏆\n"
            "Tu n'es pas encore enregistré.\n"
            "Envoie la commande /register pour créer ton profil."
        )