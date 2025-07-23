import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta
import logging
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader

# Charger les variables d'environnement
load_dotenv()
cloudinary.config(cloudinary_url=os.getenv("CLOUDINARY_URL"))

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
    logger.info("Connexion MongoDB établie avec succès")
except Exception as e:
    logger.critical(f"Échec de connexion à MongoDB: {e}")
    raise

async def find_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la commande /findmatch"""
    try:
        user = update.effective_user
        
        if not db.players.find_one({"telegram_id": user.id}):
            await update.message.reply_text("⚠️ Utilisez /register avant de chercher un match")
            return

        if db.matches.count_documents({
            "telegram_id": user.id,
            "status": "searching"
        }) > 0:
            await update.message.reply_text("🔍 Vous avez déjà une recherche en cours")
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(mode, callback_data=f"mode_{mode}")] 
            for mode in ["1v1", "2v2", "3v3"]
        ])

        await update.message.reply_text(
            "🎮 Choisissez un mode de jeu :",
            reply_markup=keyboard
        )

    except Exception as e:
        logger.error(f"Erreur find_match: {e}", exc_info=True)
        await update.message.reply_text("❌ Service indisponible. Réessayez plus tard.")

async def handle_mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la sélection du mode"""
    query = update.callback_query
    await query.answer()
    
    try:
        user = query.from_user
        mode = query.data.split("_")[1]  # "1v1", "2v2", etc.

        player = db.players.find_one({"telegram_id": user.id})
        if not player:
            await query.edit_message_text("❌ Profil non trouvé")
            return

        # Insertion atomique
        db.matches.insert_one({
            "telegram_id": user.id,
            "username": user.username,
            "mode": mode,
            "trophies": player["trophies"],
            "status": "searching",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        })

        # Notifier les autres joueurs avec un bouton "Rejoindre"
        for other in db.players.find({"telegram_id": {"$ne": user.id}}):
            try:
                await context.bot.send_message(
                    chat_id=other["telegram_id"],
                    text=f"🔔 {user.username or 'Un joueur'} cherche un match en mode {mode} !",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("Rejoindre", callback_data=f"join_{user.id}_{mode}")]
                    ])
                )
            except Exception as e:
                logger.warning(f"Impossible de notifier {other.get('username', other['telegram_id'])}: {e}")

        await query.edit_message_text(f"🔍 Recherche {mode} en cours...")

    except Exception as e:
        logger.error(f"Erreur handle_mode_selection: {e}", exc_info=True)
        await query.edit_message_text("❌ Échec de la recherche")

async def handle_join_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère le clic sur le bouton 'Rejoindre'"""
    query = update.callback_query
    await query.answer()
    try:
        data = query.data.split("_")
        creator_id = int(data[1])
        mode = data[2]
        joiner = query.from_user

        # Vérifier si le match existe et est toujours "searching"
        match = db.matches.find_one({"telegram_id": creator_id, "mode": mode, "status": "searching"})
        if not match:
            await query.edit_message_text("❌ Ce match n'est plus disponible.")
            return

        # Mettre à jour le match (exemple pour 1v1)
        db.matches.update_one(
            {"_id": match["_id"]},
            {"$set": {"status": "ready", "opponent_id": joiner.id, "opponent_username": joiner.username}}
        )

        # Notifier les deux joueurs
        await context.bot.send_message(
            chat_id=creator_id,
            text=f"✅ {joiner.username or 'Un joueur'} a rejoint votre match {mode} !"
        )
        await context.bot.send_message(
            chat_id=joiner.id,
            text=f"✅ Vous avez rejoint le match de {match.get('username', 'un joueur')} en mode {mode} !"
        )
        await query.edit_message_text("🎮 Vous avez rejoint le match !")

        # Demander la capture d'écran à chaque joueur
        for pid in [creator_id, joiner.id]:
            await context.bot.send_message(
                chat_id=pid,
                text="Merci d'envoyer la capture d'écran du résultat du match (photo uniquement)."
            )

    except Exception as e:
        logger.error(f"Erreur handle_join_match: {e}", exc_info=True)
        await query.edit_message_text("❌ Impossible de rejoindre ce match.")

async def handle_match_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la réception de la capture d'écran d'un match"""
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("Merci d'envoyer une photo.")
        return

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    # Upload sur Cloudinary
    result = cloudinary.uploader.upload(photo_bytes, folder="brawlstars_match_screens")
    photo_url = result.get("secure_url")

    # Stocke la capture dans la collection "match_screens"
    db.match_screens.insert_one({
        "telegram_id": user.id,
        "username": user.username,
        "photo_url": photo_url,
        "timestamp": datetime.utcnow()
    })

    await update.message.reply_text("✅ Capture reçue ! Elle sera publiée dans les news.")

async def news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Affiche les dernières captures de matchs dans les news"""
    news_items = db.match_screens.find().sort("timestamp", -1).limit(5)
    for item in news_items:
        await update.message.reply_photo(
            photo=item["photo_url"],
            caption=f"Match de {item.get('username', 'un joueur')} le {item['timestamp'].strftime('%d/%m/%Y %H:%M')}"
        )

def setup_handlers(application):
    application.add_handler(CommandHandler("findmatch", find_match))
    application.add_handler(CallbackQueryHandler(handle_mode_selection, pattern="^mode_"))
    application.add_handler(CallbackQueryHandler(handle_join_match, pattern="^join_"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_match_screenshot))
    application.add_handler(CommandHandler("news", news))