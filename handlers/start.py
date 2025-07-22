import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

# Charger les variables d'environnement (utile si handler lancé seul)
load_dotenv()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = MongoClient(os.getenv('MONGO_URI'))
    db = client.brawlbase

    user = update.effective_user
    db.users.update_one(
        {'telegram_id': user.id},
        {'$set': {'username': user.username}},
        upsert=True
    )
    await update.message.reply_text(f"👋 Salut {user.first_name} ! Bienvenue sur le Brawl Stars Tournament Bot ! 🏆")