import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

# Liste des ID Telegram des admins (à personnaliser)
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔️ Commande réservée aux admins.")
        return

    if not context.args:
        await update.message.reply_text("Utilisation : /ban <pseudo>")
        return

    username = " ".join(context.args).strip()
    result = db.players.delete_one({"username": {"$regex": f"^{username}$", "$options": "i"}})
    if result.deleted_count:
        await update.message.reply_text(f"✅ Joueur '{username}' banni et supprimé.")
    else:
        await update.message.reply_text(f"❌ Joueur '{username}' introuvable.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔️ Commande réservée aux admins.")
        return

    if not context.args:
        await update.message.reply_text("Utilisation : /broadcast <message>")
        return

    message = " ".join(context.args)
    count = 0
    for player in db.players.find():
        try:
            await context.bot.send_message(chat_id=player["telegram_id"], text=f"[Annonce admin]\n{message}")
            count += 1
        except Exception:
            continue
    await update.message.reply_text(f"✅ Message envoyé à {count} joueurs.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔️ Commande réservée aux admins.")
        return

    n_players = db.players.count_documents({})
    n_matches = db.matches.count_documents({})
    n_screens = db.match_screens.count_documents({})
    await update.message.reply_text(
        f"📊 Statistiques :\n"
        f"• Joueurs : {n_players}\n"
        f"• Matchs : {n_matches}\n"
        f"• Captures : {n_screens}"
    )