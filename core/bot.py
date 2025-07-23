import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler

# Charger les variables d'environnement
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

# Import du handler /start
from handlers.start import start
# Import du setup pour le formulaire d'inscription
from handlers.registration import setup as setup_registration
# Import du handler /profile
from handlers.profile import profile
# Import du handler /findall
from handlers.findall import findall
# Import du handler /search
from handlers.search import search
# Import du handler /news
from handlers.news import news

from handlers.admin import ban, broadcast, stats



def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("findall", findall))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("news", news))
    app.add_handler(CommandHandler("start", start))
    setup_registration(app)  # Ajoute le ConversationHandler pour /register
    print("Bot démarré !")
    app.run_polling()

if __name__ == "__main__":
    main()