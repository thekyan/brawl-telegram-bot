import os
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)
from pymongo import MongoClient
from bson import ObjectId
import cloudinary
import cloudinary.uploader
import logging

ASK_TEAM_NAME, ASK_MEMBER_PSEUDO, WAIT_MEMBER_ACTION, ASK_TEAM_LOGO = range(4)

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
except Exception as e:
    logger.critical(f"Échec de connexion à MongoDB: {e}")
    raise

MAX_MEMBERS = 5  # Par exemple

# ----------- Création d'une team -----------

async def start_team_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["members"] = []
    context.user_data["mode"] = "create"
    await update.message.reply_text("Quel est le nom de votre team ?")
    return ASK_TEAM_NAME

# ----------- Modification d'une team -----------

async def start_team_modify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    team = db.teams.find_one({"member_ids": user.id})
    if not team:
        await update.message.reply_text("❌ Tu n'es membre d'aucune team à modifier.")
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["team_id"] = str(team["_id"])
    context.user_data["members"] = [{"telegram_id": tid, "username": db.players.find_one({"telegram_id": tid}).get("username", str(tid))} for tid in team["member_ids"]]
    context.user_data["team_name"] = team["name"]
    context.user_data["mode"] = "modify"

    await update.message.reply_text(
        f"🔄 Modification de la team '{team['name']}'.\n"
        f"Envoie le nouveau nom de la team (ou renvoie l'ancien) :"
    )
    return ASK_TEAM_NAME

# ----------- Nom de la team -----------

async def ask_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    team_name = update.message.text.strip()
    if not team_name:
        await update.message.reply_text("❌ Merci d'entrer un nom de team valide.")
        return ASK_TEAM_NAME
    context.user_data["team_name"] = team_name
    context.user_data["members"] = []
    await update.message.reply_text("Envoie le pseudo du premier membre de la team :")
    return ASK_MEMBER_PSEUDO

# ----------- Ajout de membres -----------

async def ask_member_pseudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pseudo = update.message.text.strip().lstrip("@")
    player = db.players.find_one({"username": {"$regex": f"^{pseudo}$", "$options": "i"}})
    if not player:
        await update.message.reply_text("❌ Pseudo incorrect, veuillez réessayer.")
        return ASK_MEMBER_PSEUDO

    members = context.user_data.get("members", [])
    if player["telegram_id"] in [m["telegram_id"] for m in members]:
        await update.message.reply_text("Ce joueur est déjà dans la team.")
        return ASK_MEMBER_PSEUDO

    # Vérifie que le joueur n'a pas déjà une team (sauf si on modifie et qu'il est déjà dans celle-ci)
    if context.user_data.get("mode") == "modify":
        team_id = ObjectId(context.user_data["team_id"])
        if player.get("team_id") and player.get("team_id") != team_id:
            await update.message.reply_text("Ce joueur fait déjà partie d'une autre team.")
            return ASK_MEMBER_PSEUDO
    else:
        if player.get("team_id"):
            await update.message.reply_text("Ce joueur fait déjà partie d'une autre team.")
            return ASK_MEMBER_PSEUDO

    members.append({
        "telegram_id": player["telegram_id"],
        "username": player["username"]
    })
    context.user_data["members"] = members

    msg = f"✅ {player['username']} ajouté à la team !\n\nMembres actuels :\n"
    msg += "\n".join([f"- {m['username']}" for m in members])

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Ajouter un membre", callback_data="add_member"),
            InlineKeyboardButton("Team complète", callback_data="team_complete")
        ]
    ])
    await update.message.reply_text(msg, reply_markup=keyboard)
    return WAIT_MEMBER_ACTION

async def wait_member_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    members = context.user_data.get("members", [])
    if query.data == "add_member":
        if len(members) >= MAX_MEMBERS:
            await query.edit_message_text("La team a atteint le nombre maximum de membres.")
            await query.message.reply_text("Envoie le logo de ta team (photo uniquement) :")
            return ASK_TEAM_LOGO
        await query.edit_message_text("Envoie le pseudo du membre suivant :")
        return ASK_MEMBER_PSEUDO
    elif query.data == "team_complete":
        if len(members) < 2:
            await query.edit_message_text("Une team doit avoir au moins 2 membres.")
            return WAIT_MEMBER_ACTION
        await query.edit_message_text("Envoie le logo de ta team (photo uniquement) :")
        return ASK_TEAM_LOGO

# ----------- Logo -----------

async def ask_team_logo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Merci d'envoyer une photo pour le logo.")
        return ASK_TEAM_LOGO

    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    result = cloudinary.uploader.upload(photo_bytes, folder="brawlstars_teams")
    logo_url = result.get("secure_url")

    team_name = context.user_data["team_name"]
    member_ids = [m["telegram_id"] for m in context.user_data["members"]]

    if context.user_data.get("mode") == "modify":
        team_id = ObjectId(context.user_data["team_id"])
        db.teams.update_one(
            {"_id": team_id},
            {"$set": {"name": team_name, "member_ids": member_ids, "logo_url": logo_url}}
        )
        # Mets à jour les joueurs (enlève l'ancien team_id pour ceux qui ne sont plus dans la team)
        db.players.update_many(
            {"team_id": team_id, "telegram_id": {"$nin": member_ids}},
            {"$set": {"team_id": None}}
        )
        db.players.update_many(
            {"telegram_id": {"$in": member_ids}},
            {"$set": {"team_id": team_id}}
        )
        await update.message.reply_text(
            f"✅ Team '{team_name}' modifiée avec succès !\n"
            f"Membres : {', '.join([m['username'] for m in context.user_data['members']])}\n"
            f"Logo mis à jour."
        )
    else:
        team = {
            "name": team_name,
            "member_ids": member_ids,
            "logo_url": logo_url
        }
        team_id = db.teams.insert_one(team).inserted_id
        db.players.update_many(
            {"telegram_id": {"$in": member_ids}},
            {"$set": {"team_id": team_id}}
        )
        await update.message.reply_text(
            f"🎉 Team '{team_name}' enregistrée avec succès !\n"
            f"Membres : {', '.join([m['username'] for m in context.user_data['members']])}\n"
            f"Logo enregistré."
        )
    return ConversationHandler.END

def setup_team_registration(application):
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("registerteam", start_team_registration),
            CommandHandler("modifyteam", start_team_modify)
        ],
        states={
            ASK_TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_team_name)],
            ASK_MEMBER_PSEUDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_member_pseudo)],
            WAIT_MEMBER_ACTION: [CallbackQueryHandler(wait_member_action, pattern="^(add_member|team_complete)$")],
            ASK_TEAM_LOGO: [MessageHandler(filters.PHOTO, ask_team_logo)],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)