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

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot démarré !")
    app.run_polling()

if __name__ == "__main__":
    main()