import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler, CommandHandler, MessageHandler, filters
from datetime import datetime, timedelta
import logging
from pymongo import MongoClient
import cloudinary
import cloudinary.uploader
from bson import ObjectId

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
    """Gère la sélection du mode et demande le lien de gameroom"""
    query = update.callback_query
    await query.answer()
    try:
        user = query.from_user
        mode = query.data.split("_")[1]

        player = db.players.find_one({"telegram_id": user.id})
        if not player:
            await query.edit_message_text("❌ Profil non trouvé")
            return

        # Création du match en base
        match_id = db.matches.insert_one({
            "telegram_id": user.id,
            "username": user.username,
            "mode": mode,
            "trophies": player["trophies"],
            "status": "waiting_gameroom",
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=5)
        }).inserted_id

        # Demande au joueur de créer la gameroom et d'envoyer le lien
        context.user_data["pending_gameroom"] = {
            "match_id": str(match_id),
            "mode": mode
        }
        await query.edit_message_text(
            "🕹️ Merci de créer une salle amicale dans Brawl Stars, puis copie le lien d'invitation ici pour valider la recherche de match."
        )

    except Exception as e:
        logger.error(f"Erreur handle_mode_selection: {e}", exc_info=True)
        await query.edit_message_text("❌ Échec de la recherche")

async def handle_gameroom_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text
    pending = context.user_data.get("pending_gameroom")
    if not pending:
        return  # Ignore si pas d'attente de lien

    if not text.startswith("https://"):
        await update.message.reply_text("Merci de coller un lien d'invitation valide (commençant par https://).")
        return

    # Met à jour le match avec le lien de gameroom
    db.matches.update_one(
        {"_id": ObjectId(pending["match_id"])},
        {"$set": {"gameroom_link": text, "status": "searching"}}
    )

    await update.message.reply_text("✅ Lien de la salle enregistré ! Les autres joueurs vont pouvoir rejoindre.")

    # Notifie les autres joueurs avec le lien et bouton rejoindre
    for other in db.players.find({"telegram_id": {"$ne": user.id}}):
        try:
            await context.bot.send_message(
                chat_id=other["telegram_id"],
                text=f"🔔 {user.username or 'Un joueur'} cherche un match {pending['mode']} !\n"
                     f"Rejoins la salle amicale avec ce lien :\n{text}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Rejoindre", callback_data=f"join_{user.id}_{pending['mode']}")]
                ])
            )
        except Exception:
            continue

    context.user_data.pop("pending_gameroom", None)

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

        # Mettre à jour le match
        db.matches.update_one(
            {"_id": match["_id"]},
            {"$set": {"status": "ready", "opponent_id": joiner.id, "opponent_username": joiner.username}}
        )

        # Notifier les deux joueurs avec le pseudo complet de celui qui rejoint
        await context.bot.send_message(
            chat_id=creator_id,
            text=f"✅ {joiner.full_name} (@{joiner.username or 'aucun pseudo'}) a rejoint votre match {mode} !"
        )
        await context.bot.send_message(
            chat_id=joiner.id,
            text=f"✅ Tu as rejoint le match de {match.get('username', 'un joueur')} en mode {mode} !"
        )
        await query.edit_message_text("🎮 Tu as rejoint le match !")

        # Bouton "Fin de match" pour les deux joueurs
        for pid in [creator_id, joiner.id]:
            await context.bot.send_message(
                chat_id=pid,
                text="Quand le match est terminé, appuie sur le bouton ci-dessous.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Fin de match", callback_data=f"endmatch_{str(match['_id'])}")]
                ])
            )

    except Exception as e:
        logger.error(f"Erreur handle_join_match: {e}", exc_info=True)
        await query.edit_message_text("❌ Impossible de rejoindre ce match.")

async def handle_end_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_id = query.data.split("_")[1]
    user = query.from_user

    # Demande à l'utilisateur s'il a gagné ou perdu
    await query.edit_message_text(
        "Résultat du match ?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Victoire", callback_data=f"result_{match_id}_win")],
            [InlineKeyboardButton("Défaite", callback_data=f"result_{match_id}_lose")]
        ])
    )

async def handle_match_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, match_id, result = query.data.split("_")
    user = query.from_user

    # Stocke la réponse temporairement dans la collection match_results
    db.match_results.update_one(
        {"match_id": match_id, "telegram_id": user.id},
        {"$set": {"result": result, "answered": True}},
        upsert=True
    )

    await query.edit_message_text("Merci ! Envoie maintenant la capture d'écran du résultat du match (photo uniquement).")

async def handle_match_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message.photo:
        await update.message.reply_text("Merci d'envoyer une photo.")
        return

    # Trouve le dernier match en attente de résultat pour ce joueur
    result = db.match_results.find_one({"telegram_id": user.id, "answered": True, "screenshot": {"$exists": False}})
    if not result:
        await update.message.reply_text("Aucun match à valider ou capture déjà envoyée.")
        return

    match_id = result["match_id"]

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    # Upload sur Cloudinary
    result_cloud = cloudinary.uploader.upload(photo_bytes, folder="brawlstars_match_screens")
    photo_url = result_cloud.get("secure_url")

    # Stocke la capture
    db.match_results.update_one(
        {"match_id": match_id, "telegram_id": user.id},
        {"$set": {"screenshot": photo_url}}
    )

    await update.message.reply_text("✅ Capture reçue !")

    # Vérifie si les deux joueurs ont répondu et envoyé la capture
    match = db.matches.find_one({"_id": ObjectId(match_id)})
    if not match:
        return
    ids = [match["telegram_id"], match["opponent_id"]]
    results = list(db.match_results.find({"match_id": match_id, "telegram_id": {"$in": ids}}))

    if len(results) == 2 and all("screenshot" in r for r in results):
        # Met à jour les stats
        for r in results:
            win = 1 if r["result"] == "win" else 0
            lose = 1 if r["result"] == "lose" else 0
            db.players.update_one({"telegram_id": r["telegram_id"]}, {
                "$inc": {"matches_played": 1, "wins": win, "defeats": lose}
            })
        db.matches.update_one({"_id": ObjectId(match_id)}, {"$set": {"status": "finished"}})
        # Notifie les deux joueurs
        for pid in ids:
            await context.bot.send_message(pid, "🎉 Match terminé, statistiques mises à jour !")

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gameroom_link))
    application.add_handler(CallbackQueryHandler(handle_join_match, pattern="^join_"))
    application.add_handler(CallbackQueryHandler(handle_end_match, pattern="^endmatch_"))
    application.add_handler(CallbackQueryHandler(handle_match_result, pattern="^result_"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_match_screenshot))
    application.add_handler(CommandHandler("news", news))