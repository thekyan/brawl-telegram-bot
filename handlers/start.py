import os
from pymongo import MongoClient
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv('MONGO_URI'))
db = client.brawlbase

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = db.players.find_one({'telegram_id': user.id})

    if player:
        msg =(
    f"""👋 Salut {player.get('username', user.first_name)} ! Ravi de te revoir sur le Brawl Stars Tournament Bot ! 🏆

        Voici la liste des différentes commandes disponibles :
        - /register : Créer ton profil
        - /registerteam : Créer une team
        - /modifyteam : Modifier ta team
        - /profileteam : Voir le profil de ta team
        - /findallteam : Voir toutes les teams
        - /searchteam <nom> : Rechercher une team
        - /scrim : Lancer un scrim
        - /findmatch : Trouver un match
        - /search : Rechercher un joueur
        - /profile : Voir ton profil
        - /findall : Voir tous les joueurs enregistrés
        - /news : Voir les dernières nouvelles
        - /freindly : Lancer une partie amicale
        - /createtournament : Créer un tournoi (admin)
        - /jointournament <admin> : Rejoindre un tournoi
        - /tournaments : Voir les tournois
        - /closetournament <admin> : Clôturer un tournoi (admin)

        Nous vous souhaitons de passer un bon moment avec nous !
        """
        )
        # Affiche la photo si elle existe
        if player.get("profile_photo"):
            await update.message.reply_photo(
                photo=player["profile_photo"],
                caption=msg
            )
        else:
            await update.message.reply_text(msg)
    else:
        await update.message.reply_text(
            f"👋 Salut {user.first_name} ! Bienvenue sur le Brawl Stars Tournament Bot ! 🏆\n"
            "Tu n'es pas encore enregistré.\n"
            "Envoie la commande /register pour créer ton profil."
        )