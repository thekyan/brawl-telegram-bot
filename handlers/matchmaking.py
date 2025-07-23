import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler
from datetime import datetime
import logging
from pymongo import MongoClient

# Charger les variables d'environnement
load_dotenv()

# Configuration MongoDB depuis .env
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "brawl_stars")

try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    # Test de connexion
    db.command('ping')
    logger.info("Connexion MongoDB établie avec succès")
except Exception as e:
    logger.critical(f"Échec de connexion à MongoDB: {e}")
    raise

# Configurer le logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def find_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gère la commande /findmatch"""
    try:
        user = update.effective_user
        
        if not db.players.find_one({"telegram_id": user.id}):
            await update.message.reply_text("⚠️ Utilisez /register avant de chercher un match")
            return

        if db.matches.count_documents({
            "players.telegram_id": user.id,
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
            "expires_at": datetime.utcnow() + timedelta(minutes=5)  # Timeout
        })

        await query.edit_message_text(f"🔍 Recherche {mode} en cours...")

        # Démarrer le job de matching
        context.job_queue.run_once(
            callback=match_player,
            when=5,
            data={'user_id': user.id, 'mode': mode},
            name=f"matchmaking_{user.id}"
        )

    except Exception as e:
        logger.error(f"Erreur handle_mode_selection: {e}", exc_info=True)
        await query.edit_message_text("❌ Échec de la recherche")

def setup_handlers(application):
    application.add_handler(CommandHandler("findmatch", find_match))
    application.add_handler(CallbackQueryHandler(
        handle_mode_selection, 
        pattern="^mode_"
    ))