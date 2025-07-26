async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Utilisation : /search <pseudo>")
        return

    username = " ".join(context.args).strip()
    player = db.players.find_one({"username": {"$regex": f"^{username}$", "$options": "i"}})

    if not player:
        await update.message.reply_text(f"Aucun joueur trouvé avec le pseudo : {username}")
        return

    # Récupère la team si elle existe
    team_name = None
    if player.get("team_id"):
        team = db.teams.find_one({"_id": player["team_id"]})
        if team:
            team_name = team.get("name")

    msg = (
        f"👤 Pseudo : {player.get('username', 'Inconnu')}\n"
        f"• Pays : {player.get('country', 'N/A')}\n"
        f"• Team : {team_name if team_name else 'Aucune'}\n"
        f"• Trophées : {player.get('trophies', 'N/A')}\n"
        f"• Brawler principal : {player.get('main_brawler', 'N/A')}\n"
        f"• Victoires : {player.get('wins', 0)}\n"
        f"• Défaites : {player.get('defeats', 0)}\n"
        f"• Matchs joués : {player.get('matches_played', 0)}\n"
        f"• Inscrit le : {player.get('registered_at', datetime.utcnow()).strftime('%d/%m/%Y %H:%M')}\n"
    )
    if player.get("profile_photo"):
        await update.message.reply_photo(photo=player["profile_photo"], caption=msg)
    else:
        await update.message.reply_text(msg)