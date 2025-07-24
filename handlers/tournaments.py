import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

# Liste des admins (à adapter)
ADMIN_IDS = [123456789]  # Remplace par ton telegram_id ou ceux des admins

# États du formulaire tournoi
ASK_TOURNAMENT_NAME, ASK_COMPETITION_TYPE, ASK_MODE, ASK_TEAMS, CONFIRM = range(5)

async def admin_only(update: Update):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Seul l'administrateur peut gérer les tournois.")
        return False
    return True

async def start_tournament_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await admin_only(update):
        return ConversationHandler.END
    context.user_data.clear()
    await update.message.reply_text("Nom du tournoi ?")
    return ASK_TOURNAMENT_NAME

async def ask_tournament_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tournament_name"] = update.message.text.strip()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Élimination directe", callback_data="type_elimination")],
        [InlineKeyboardButton("Poules", callback_data="type_poules")]
    ])
    await update.message.reply_text("Type de compétition ?", reply_markup=keyboard)
    return ASK_COMPETITION_TYPE

async def ask_competition_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    comp_type = "Élimination directe" if query.data == "type_elimination" else "Poules"
    context.user_data["competition_type"] = comp_type
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1v1", callback_data="mode_1v1")],
        [InlineKeyboardButton("2v2", callback_data="mode_2v2")],
        [InlineKeyboardButton("3v3", callback_data="mode_3v3")]
    ])
    await query.edit_message_text("Mode de jeu ?", reply_markup=keyboard)
    return ASK_MODE

async def ask_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    mode = query.data.split("_")[1]
    context.user_data["mode"] = mode

    # Affiche la liste des teams disponibles
    teams = list(db.teams.find())
    if not teams:
        await query.edit_message_text("Aucune team enregistrée.")
        return ConversationHandler.END

    context.user_data["selected_teams"] = []
    msg = "Sélectionne les teams participantes (clique sur chaque team, puis 'Valider') :\n"
    keyboard = [
        [InlineKeyboardButton(team["name"], callback_data=f"team_{str(team['_id'])}")]
        for team in teams
    ]
    keyboard.append([InlineKeyboardButton("Valider la sélection", callback_data="validate_teams")])
    await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    return ASK_TEAMS

async def ask_teams(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("team_"):
        team_id = data.split("_")[1]
        if team_id not in context.user_data["selected_teams"]:
            context.user_data["selected_teams"].append(team_id)
        await query.answer("Team ajoutée à la sélection.")
        return ASK_TEAMS

    if data == "validate_teams":
        if not context.user_data["selected_teams"]:
            await query.answer("Sélectionne au moins une team.")
            return ASK_TEAMS
        # Récapitulatif
        team_names = [
            db.teams.find_one({"_id": team_id}).get("name", str(team_id))
            for team_id in context.user_data["selected_teams"]
        ]
        msg = (
            f"✅ Récapitulatif du tournoi :\n"
            f"• Nom : {context.user_data['tournament_name']}\n"
            f"• Type : {context.user_data['competition_type']}\n"
            f"• Mode : {context.user_data['mode']}\n"
            f"• Teams : {', '.join(team_names)}\n\n"
            f"Confirmer la création ?"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirmer", callback_data="confirm_tournament")],
            [InlineKeyboardButton("Annuler", callback_data="cancel_tournament")]
        ])
        await query.edit_message_text(msg, reply_markup=keyboard)
        return CONFIRM

async def confirm_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_tournament":
        # Enregistre le tournoi
        db.tournaments.insert_one({
            "name": context.user_data["tournament_name"],
            "competition_type": context.user_data["competition_type"],
            "mode": context.user_data["mode"],
            "team_ids": context.user_data["selected_teams"],
            "created_by": query.from_user.id
        })
        await query.edit_message_text("✅ Tournoi créé avec succès !")
    else:
        await query.edit_message_text("Création du tournoi annulée.")
    return ConversationHandler.END

def setup_tournament_handlers(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("createtournament", start_tournament_creation)],
        states={
            ASK_TOURNAMENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_tournament_name)],
            ASK_COMPETITION_TYPE: [CallbackQueryHandler(ask_competition_type, pattern="^type_")],
            ASK_MODE: [CallbackQueryHandler(ask_mode, pattern="^mode_")],
            ASK_TEAMS: [CallbackQueryHandler(ask_teams, pattern="^(team_|validate_teams)")],
            CONFIRM: [CallbackQueryHandler(confirm_tournament, pattern="^(confirm_tournament|cancel_tournament)$")],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)