import os
from pymongo import MongoClient
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters
)
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

ASK_OPPONENT, ASK_TIME, CONFIRM_MEMBERS, WAIT_LINKS, ASK_SCORE, ASK_SCREENSHOTS = range(6)

async def start_scrim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({"telegram_id": user.id})
    if not player or not player.get("team_id"):
        await update.message.reply_text("❌ Tu dois être membre d'une team pour demander un scrim.")
        return ConversationHandler.END
    context.user_data["creator_id"] = user.id
    context.user_data["team_id"] = player["team_id"]
    await update.message.reply_text("Quel est le nom de la team que tu veux affronter ?")
    return ASK_OPPONENT

async def ask_opponent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    opponent_name = update.message.text.strip()
    opponent_team = db.teams.find_one({"name": {"$regex": f"^{opponent_name}$", "$options": "i"}})
    if not opponent_team:
        await update.message.reply_text("❌ Nom de team incorrect. Réessaie.")
        return ASK_OPPONENT
    context.user_data["opponent_team_id"] = opponent_team["_id"]
    context.user_data["opponent_team_name"] = opponent_team["name"]
    await update.message.reply_text("À quelle heure (GMT+1) veux-tu jouer le scrim ? (ex: 21:30)")
    return ASK_TIME

async def ask_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        hour, minute = map(int, time_str.split(":"))
        now = datetime.now()
        scrim_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scrim_time < now:
            scrim_time += timedelta(days=1)
        context.user_data["scrim_time"] = scrim_time
    except Exception:
        await update.message.reply_text("❌ Heure invalide. Format attendu : HH:MM (ex: 21:30)")
        return ASK_TIME

    # Prépare la liste des membres à confirmer
    my_team = db.teams.find_one({"_id": context.user_data["team_id"]})
    opponent_team = db.teams.find_one({"_id": context.user_data["opponent_team_id"]})
    context.user_data["my_team_name"] = my_team["name"]
    context.user_data["my_team_members"] = my_team["member_ids"]
    context.user_data["opponent_team_members"] = opponent_team["member_ids"]
    context.user_data["confirmed"] = set()

    # Notifie tous les membres des deux teams pour confirmation
    for tid in my_team["member_ids"] + opponent_team["member_ids"]:
        await context.bot.send_message(
            chat_id=tid,
            text=f"⚔️ Demande de scrim entre {my_team['name']} et {opponent_team['name']} à {scrim_time.strftime('%H:%M')} (GMT+1).\n"
                 "Clique sur le bouton pour confirmer ta participation.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Je confirme", callback_data="confirm_scrim")]
            ])
        )
    await update.message.reply_text("Des demandes de confirmation ont été envoyées à tous les membres des deux teams.")
    return CONFIRM_MEMBERS

async def confirm_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    context.user_data.setdefault("confirmed", set())
    context.user_data["confirmed"].add(user_id)
    await query.answer("Confirmation enregistrée !")
    # Vérifie si tous les membres ont confirmé
    all_members = set(context.user_data["my_team_members"] + context.user_data["opponent_team_members"])
    if context.user_data["confirmed"] >= all_members:
        scrim_time = context.user_data["scrim_time"]
        await context.bot.send_message(
            chat_id=context.user_data["creator_id"],
            text=f"✅ Tous les membres ont confirmé ! Le scrim est enregistré pour {scrim_time.strftime('%H:%M')} (GMT+1).\n"
                 "Tu recevras une notification 5 minutes avant pour donner le lien de la gameroom et le lien spectateur."
        )
        # Notifie tous les joueurs du bot
        for player in db.players.find():
            await context.bot.send_message(
                chat_id=player["telegram_id"],
                text=f"📢 Un scrim opposant {context.user_data['my_team_name']} à {context.user_data['opponent_team_name']} aura lieu à {scrim_time.strftime('%H:%M')} (GMT+1) !"
            )
        # Lance le timer pour la notification 5 minutes avant
        asyncio.create_task(scrim_reminder(context))
        return WAIT_LINKS
    else:
        await query.edit_message_text("Merci, ta confirmation est prise en compte.")
        return CONFIRM_MEMBERS

async def scrim_reminder(context):
    scrim_time = context.user_data["scrim_time"]
    wait_seconds = (scrim_time - timedelta(minutes=5) - datetime.now()).total_seconds()
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    creator_id = context.user_data["creator_id"]
    await context.bot.send_message(
        chat_id=creator_id,
        text="⏰ Merci d'envoyer le lien de la gameroom Brawl Stars et le lien spectateur (séparés par un espace ou un retour à la ligne)."
    )

async def wait_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    parts = text.split()
    if len(parts) < 2:
        await update.message.reply_text("Merci d'envoyer les deux liens (gameroom et spec).")
        return WAIT_LINKS
    gameroom_link, spec_link = parts[0], parts[1]
    context.user_data["gameroom_link"] = gameroom_link
    context.user_data["spec_link"] = spec_link

    my_team = db.teams.find_one({"_id": context.user_data["team_id"]})
    opponent_team = db.teams.find_one({"_id": context.user_data["opponent_team_id"]})
    my_members = list(db.players.find({"telegram_id": {"$in": my_team["member_ids"]}}))
    opp_members = list(db.players.find({"telegram_id": {"$in": opponent_team["member_ids"]}}))

    # Envoie aux membres des deux teams
    for m in my_members + opp_members:
        await context.bot.send_message(
            chat_id=m["telegram_id"],
            text=f"🎮 Scrim Room : {gameroom_link}\nLien spectateur : {spec_link}\n"
                 f"Adversaires : {my_team['name']} vs {opponent_team['name']}\n"
                 f"Joueurs :\n"
                 f"{', '.join([mm['username'] for mm in my_members])} vs {', '.join([om['username'] for om in opp_members])}\n"
                 f"Heure : {context.user_data['scrim_time'].strftime('%H:%M')} (GMT+1)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Lancer la partie", callback_data="start_scrim_game")],
                [InlineKeyboardButton("Fin de la partie", callback_data="end_scrim_game")]
            ])
        )

    # Envoie à tous les autres joueurs (hors les deux teams)
    all_team_ids = set(my_team["member_ids"] + opponent_team["member_ids"])
    for player in db.players.find({"telegram_id": {"$nin": list(all_team_ids)}}):
        await context.bot.send_message(
            chat_id=player["telegram_id"],
            text=f"👀 Un scrim va commencer !\n"
                 f"{my_team['name']} vs {opponent_team['name']} à {context.user_data['scrim_time'].strftime('%H:%M')} (GMT+1)\n"
                 f"Joueurs : {', '.join([mm['username'] for mm in my_members])} vs {', '.join([om['username'] for om in opp_members])}\n"
                 f"Lien spectateur : {spec_link}"
        )
    return ConversationHandler.END

async def start_scrim_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("Bonne chance ! Le message reste affiché pour tous.")

async def end_scrim_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    creator_id = context.user_data["creator_id"]
    await context.bot.send_message(
        chat_id=creator_id,
        text="La partie est terminée ! Merci d'envoyer le score final (ex: 3-2)."
    )
    context.user_data["score_reporter"] = creator_id
    return ASK_SCORE

async def ask_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    score = update.message.text.strip()
    context.user_data["score"] = score
    await update.message.reply_text("Merci ! Envoie maintenant les captures d'écran des résultats (envoie toutes les images, puis tape /done quand tu as fini).")
    context.user_data["screenshots"] = []
    return ASK_SCREENSHOTS

async def ask_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        # Ici tu peux uploader sur cloudinary ou stocker le binaire, exemple:
        # file = await update.message.photo[-1].get_file()
        # photo_bytes = await file.download_as_bytearray()
        # result = cloudinary.uploader.upload(photo_bytes, folder="scrim_results")
        # url = result.get("secure_url")
        url = "screenshot_url_placeholder"  # Remplace par l'URL réelle si tu utilises cloudinary
        context.user_data["screenshots"].append(url)
        await update.message.reply_text("Capture reçue. Envoie-en d'autres ou tape /done si tu as fini.")
        return ASK_SCREENSHOTS
    else:
        await update.message.reply_text("Merci d'envoyer une image ou /done si tu as terminé.")
        return ASK_SCREENSHOTS

async def done_screenshots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Met à jour les profils des joueurs (victoires/défaites/matchs joués)
    my_team = db.teams.find_one({"_id": context.user_data["team_id"]})
    opponent_team = db.teams.find_one({"_id": context.user_data["opponent_team_id"]})
    my_members = list(db.players.find({"telegram_id": {"$in": my_team["member_ids"]}}))
    opp_members = list(db.players.find({"telegram_id": {"$in": opponent_team["member_ids"]}}))

    # Détermine le gagnant (ex: "3-2" => 3 > 2)
    score = context.user_data.get("score", "0-0")
    try:
        score1, score2 = map(int, score.replace(" ", "").split("-"))
    except Exception:
        score1, score2 = 0, 0

    if score1 > score2:
        winners, losers = my_members, opp_members
    elif score2 > score1:
        winners, losers = opp_members, my_members
    else:
        winners, losers = [], []

    for p in my_members + opp_members:
        db.players.update_one(
            {"telegram_id": p["telegram_id"]},
            {"$inc": {"matches_played": 1}}
        )
    for p in winners:
        db.players.update_one(
            {"telegram_id": p["telegram_id"]},
            {"$inc": {"wins": 1}}
        )
    for p in losers:
        db.players.update_one(
            {"telegram_id": p["telegram_id"]},
            {"$inc": {"defeats": 1}}
        )

    await update.message.reply_text("✅ Résultat enregistré et profils mis à jour !")
    # Tu peux aussi enregistrer le scrim dans une collection dédiée ici

    return ConversationHandler.END

def setup_scrim(application):
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("scrim", start_scrim)],
        states={
            ASK_OPPONENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_opponent)],
            ASK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_time)],
            CONFIRM_MEMBERS: [CallbackQueryHandler(confirm_member, pattern="^confirm_scrim$")],
            WAIT_LINKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, wait_links)],
            ASK_SCORE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_score)],
            ASK_SCREENSHOTS: [
                MessageHandler(filters.PHOTO, ask_screenshots),
                CommandHandler("done", done_screenshots)
            ],
            # Boutons de partie
            CONFIRM_MEMBERS: [CallbackQueryHandler(end_scrim_game, pattern="^end_scrim_game$")],
            WAIT_LINKS: [CallbackQueryHandler(end_scrim_game, pattern="^end_scrim_game$")],
            WAIT_LINKS: [CallbackQueryHandler(start_scrim_game, pattern="^start_scrim_game$")],
        },
        fallbacks=[],
        allow_reentry=True,
    )
    application.add_handler(conv_handler)