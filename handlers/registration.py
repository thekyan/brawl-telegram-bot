from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from datetime import datetime
from pymongo import MongoClient
import os
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloudinary_url=os.getenv("CLOUDINARY_URL")
)
client = MongoClient(os.getenv('MONGO_URI'))
db = client.brawlbase

# États de la conversation
ASK_USERNAME, ASK_TROPHIES, ASK_BRAWLER, ASK_PHOTO = range(4)

async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({'telegram_id': user.id})
    if player:
        await update.message.reply_text(
            f"✅ Tu es déjà inscrit sous le pseudo : {player.get('username', 'inconnu')}.\n"
            "Si tu veux modifier ton profil, utilise /modify."
        )
        return ConversationHandler.END

    await update.message.reply_text("Quel est ton pseudo Brawl Stars ?")
    return ASK_USERNAME

async def start_modify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({'telegram_id': user.id})
    if not player:
        await update.message.reply_text(
            "❌ Tu n'es pas encore inscrit. Utilise /register pour créer ton profil."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"🔄 Modification de ton profil.\n"
        f"Ton pseudo actuel est : {player.get('username', 'inconnu')}.\n"
        "Quel est ton nouveau pseudo Brawl Stars ? (ou renvoie l'ancien)"
    )
    return ASK_USERNAME

async def ask_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    context.user_data['username'] = username
    await update.message.reply_text("Combien as-tu de trophées ?")
    return ASK_TROPHIES

async def ask_trophies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        trophies = int(update.message.text)
        if trophies < 0 or trophies > 250000:
            raise ValueError
        context.user_data['trophies'] = trophies
        await update.message.reply_text("Quel est ton brawler principal ?")
        return ASK_BRAWLER
    except ValueError:
        await update.message.reply_text("❌ Merci d'entrer un nombre de trophées valide (0 à 250000).")
        return ASK_TROPHIES

async def ask_brawler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    main_brawler = update.message.text.strip()
    context.user_data['main_brawler'] = main_brawler
    await update.message.reply_text("Envoie la photo de ton profil Brawl Stars.")
    return ASK_PHOTO

async def ask_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    trophies = context.user_data['trophies']
    username = context.user_data['username']
    main_brawler = context.user_data['main_brawler']

    photo_url = None

    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        # Upload sur Cloudinary
        result = cloudinary.uploader.upload(photo_bytes, folder="brawlstars_profiles")
        photo_url = result.get("secure_url")

    player_data = {
        "telegram_id": user.id,
        "username": username,
        "trophies": trophies,
        "main_brawler": main_brawler,
        "profile_photo": photo_url,
        "registered_at": datetime.utcnow(),
        "last_active": datetime.utcnow(),
        "matches_played": 0,
        "wins": 0
    }

    db.players.update_one(
        {"telegram_id": user.id},
        {"$set": player_data},
        upsert=True
    )

    await update.message.reply_text(
        f"🎉 Profil enregistré/modifié !\n"
        f"• Pseudo : {username}\n"
        f"• Trophées: {trophies}\n"
        f"• Brawler principal: {main_brawler}\n"
        f"{'• Photo enregistrée !' if photo_url else '• Pas de photo.'}\n"
        f"Utilise /findmatch pour commencer !"
    )
    return ConversationHandler.END

async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Si l'utilisateur ne veut pas mettre de photo
    return await ask_photo(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Inscription/modification annulée.")
    return ConversationHandler.END

def setup(application):
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("register", start_register),
            CommandHandler("modify", start_modify)
        ],
        states={
            ASK_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_username)],
            ASK_TROPHIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_trophies)],
            ASK_BRAWLER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_brawler)],
            ASK_PHOTO: [
                MessageHandler(filters.PHOTO, ask_photo),
                CommandHandler("skip", skip_photo)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    application.add_handler(conv_handler)