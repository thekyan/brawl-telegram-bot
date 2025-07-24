import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler,
    filters, ConversationHandler
)
from datetime import datetime
import logging
from pymongo import MongoClient
from bson import ObjectId

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "brawlbase")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    db.command('ping')
except Exception as e:
    logger.critical(f"Échec de connexion à MongoDB: {e}")
    raise

MAX_PLAYERS = 5  # 1 créateur + 4 amis max

# États pour le ConversationHandler
WAITING_FRIENDS = 2001
WAITING_VOICE_LINK = 2002
WAITING_BRAWL_LINK = 2003

async def freindly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Propose deux choix pour lancer une partie amicale"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Inviter des amis (entrer les pseudos)", callback_data="freindly_manual")],
        [InlineKeyboardButton("Inviter tout le monde", callback_data="freindly_all")]
    ])
    await update.message.reply_text(
        "Comment veux-tu inviter les joueurs ?",
        reply_markup=keyboard
    )
    return ConversationHandler.END  # La suite est gérée par les callbacks

async def handle_manual_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["freindly_mode"] = "manual"
    await query.edit_message_text(
        f"Envoie les pseudos Telegram de tes amis à inviter (jusqu'à {MAX_PLAYERS-1}, séparés par des espaces ou des virgules) :"
    )
    return WAITING_FRIENDS

async def handle_freindly_invites(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if context.user_data.get("freindly_mode") != "manual":
        return ConversationHandler.END

    pseudos = [p.strip().lstrip("@") for p in update.message.text.replace(",", " ").split()]
    if not (1 <= len(pseudos) <= MAX_PLAYERS-1):
        await update.message.reply_text(f"Merci d'envoyer entre 1 et {MAX_PLAYERS-1} pseudo(s).")
        return WAITING_FRIENDS

    invited = []
    for pseudo in pseudos:
        player = db.players.find_one({"username": {"$regex": f"^{pseudo}$", "$options": "i"}})
        if player:
            invited.append(player["telegram_id"])
        else:
            await update.message.reply_text(f"❌ Joueur '{pseudo}' introuvable.")
            return WAITING_FRIENDS

    match_id = db.freindly_matches.insert_one({
        "creator_id": user.id,
        "creator_username": user.username,
        "invited_ids": invited,
        "joined_ids": [user.id],
        "status": "waiting",
        "created_at": datetime.utcnow()
    }).inserted_id

    for tid in invited:
        try:
            await context.bot.send_message(
                chat_id=tid,
                text=f"🎉 {user.full_name} (@{user.username}) t'invite à une partie amicale !",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Rejoindre la Game Room", callback_data=f"freindly_join_{match_id}")]
                ])
            )
        except Exception:
            continue

    await update.message.reply_text("Invitations envoyées à tes amis. Ils doivent accepter pour rejoindre la Game Room.")
    return ConversationHandler.END

async def handle_invite_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    context.user_data["freindly_mode"] = "all"

    match_id = db.freindly_matches.insert_one({
        "creator_id": user.id,
        "creator_username": user.username,
        "invited_ids": [],
        "joined_ids": [user.id],
        "status": "waiting_all",
        "created_at": datetime.utcnow()
    }).inserted_id

    # Notifie tous les joueurs sauf le créateur
    for player in db.players.find({"telegram_id": {"$ne": user.id}}):
        try:
            await context.bot.send_message(
                chat_id=player["telegram_id"],
                text=f"🎉 {user.full_name} (@{user.username}) organise une partie amicale ! Clique pour rejoindre (places limitées à {MAX_PLAYERS} joueurs) :",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Rejoindre la Game Room", callback_data=f"freindly_join_{match_id}")]
                ])
            )
        except Exception:
            continue

    await query.edit_message_text("Invitation envoyée à tout le monde ! Les premiers à accepter rejoindront la Game Room.")
    return ConversationHandler.END

async def handle_freindly_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    match_id = query.data.split("_")[2]

    match = db.freindly_matches.find_one({"_id": ObjectId(match_id)})
    if not match or user.id in match.get("joined_ids", []):
        await query.edit_message_text("Impossible de rejoindre cette Game Room.")
        return

    # Limite le nombre de joueurs
    if len(match["joined_ids"]) >= MAX_PLAYERS:
        await query.edit_message_text("La Game Room est déjà complète.")
        return

    db.freindly_matches.update_one(
        {"_id": ObjectId(match_id)},
        {"$addToSet": {"joined_ids": user.id}}
    )

    # Affiche au créateur la liste des joueurs et combien il en manque
    match = db.freindly_matches.find_one({"_id": ObjectId(match_id)})
    joined_ids = match["joined_ids"]
    joined_players = list(db.players.find({"telegram_id": {"$in": joined_ids}}))
    joined_usernames = [p.get("username", str(p["telegram_id"])) for p in joined_players]
    nb_restants = MAX_PLAYERS - len(joined_ids)

    if len(joined_ids) == MAX_PLAYERS:
        # Tous les joueurs sont là, demande le salon vocal
        await context.bot.send_message(
            chat_id=match["creator_id"],
            text=f"Tous les joueurs sont prêts !\nParticipants : {', '.join(joined_usernames)}\nLance un salon vocal dans un groupe Telegram et envoie ici le lien d'invitation du salon vocal."
        )
        db.freindly_matches.update_one(
            {"_id": ObjectId(match_id)},
            {"$set": {"status": "waiting_voice"}}
        )
        return WAITING_VOICE_LINK
    else:
        await context.bot.send_message(
            chat_id=match["creator_id"],
            text=f"Joueurs ayant accepté : {', '.join(joined_usernames)}\nIl manque encore {nb_restants} joueur(s) pour lancer la partie."
        )
        await query.edit_message_text("Tu as rejoint la Game Room. En attente des autres joueurs...")

async def handle_voice_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    match = db.freindly_matches.find_one({"creator_id": user.id, "status": "waiting_voice"})
    if not match:
        return ConversationHandler.END

    db.freindly_matches.update_one(
        {"_id": match["_id"]},
        {"$set": {"voice_link": text, "status": "voice_ready"}}
    )

    all_ids = set(match["joined_ids"])
    for pid in all_ids:
        try:
            await context.bot.send_message(
                chat_id=pid,
                text=f"🔊 Salon vocal lancé ! Rejoignez la discussion ici :\n{text}"
            )
        except Exception:
            continue

    await context.bot.send_message(
        chat_id=match["creator_id"],
        text="Envoie maintenant le lien de la Game Room Brawl Stars pour que tout le monde puisse rejoindre la partie."
    )
    db.freindly_matches.update_one(
        {"_id": match["_id"]},
        {"$set": {"status": "waiting_brawl_link"}}
    )
    return WAITING_BRAWL_LINK

async def handle_brawl_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    match = db.freindly_matches.find_one({"creator_id": user.id, "status": "waiting_brawl_link"})
    if not match:
        return ConversationHandler.END

    db.freindly_matches.update_one(
        {"_id": match["_id"]},
        {"$set": {"brawl_link": text, "status": "ready"}}
    )

    all_ids = set(match["joined_ids"])
    for pid in all_ids:
        try:
            await context.bot.send_message(
                chat_id=pid,
                text=f"🎮 Voici le lien de la Game Room Brawl Stars :\n{text}"
            )
        except Exception:
            continue
    return ConversationHandler.END

def setup_freindly_handlers(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("freindly", freindly)],
        states={
            WAITING_FRIENDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_freindly_invites)],
            WAITING_VOICE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_voice_link)],
            WAITING_BRAWL_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_brawl_link)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(handle_manual_invite, pattern="^freindly_manual$"))
    application.add_handler(CallbackQueryHandler(handle_invite_all, pattern="^freindly_all$"))
    application.add_handler(CallbackQueryHandler(handle_freindly_join, pattern="^freindly_join_"))