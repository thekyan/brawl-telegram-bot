import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client[os.getenv("DB_NAME", "brawlbase")]

async def profileteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({"telegram_id": user.id})
    if not player or not player.get("team_id"):
        await update.message.reply_text("❌ Tu n'es membre d'aucune team.")
        return

    team = db.teams.find_one({"_id": player["team_id"]})
    if not team:
        await update.message.reply_text("❌ Team introuvable.")
        return

    members = db.players.find({"telegram_id": {"$in": team["member_ids"]}})
    member_list = "\n".join([
        f"- {m.get('username', str(m['telegram_id']))} ({m.get('trophies', 0)} trophées)"
        for m in members
    ])

    msg = (
        f"🏆 **Profil de ta team**\n"
        f"• Nom : {team.get('name', 'Inconnu')}\n"
        f"• Membres :\n{member_list}\n"
    )
    if team.get("logo_url"):
        await update.message.reply_photo(photo=team["logo_url"], caption=msg)
    else:
        await update.message.reply_text(msg)

async def findallteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teams = db.teams.find()
    msg = "📋 **Liste des teams enregistrées :**\n"
    found = False
    for team in teams:
        found = True
        msg += f"\n• {team.get('name', 'Inconnu')} ({len(team.get('member_ids', []))} membres)"
    if not found:
        msg += "\nAucune team trouvée."
    await update.message.reply_text(msg)

async def searchteam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Utilisation : /searchteam <nom de la team>")
        return
    search = " ".join(args)
    team = db.teams.find_one({"name": {"$regex": search, "$options": "i"}})
    if not team:
        await update.message.reply_text("Aucune team trouvée avec ce nom.")
        return
    members = db.players.find({"telegram_id": {"$in": team["member_ids"]}})
    member_list = "\n".join([
        f"- {m.get('username', str(m['telegram_id']))} ({m.get('trophies', 0)} trophées)"
        for m in members
    ])
    msg = (
        f"🔎 **Résultat de la recherche :**\n"
        f"• Nom : {team.get('name', 'Inconnu')}\n"
        f"• Membres :\n{member_list}\n"
    )
    if team.get("logo_url"):
        await update.message.reply_photo(photo=team["logo_url"], caption=msg)
    else:
        await update.message.reply_text(msg)

def setup_team_finders(application):
    application.add_handler(CommandHandler("profileteam", profileteam))
    application.add_handler(CommandHandler("findallteam", findallteam))
    application.add_handler(CommandHandler("searchteam", searchteam))