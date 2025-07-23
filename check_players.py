from pymongo import MongoClient

# Mets ici exactement la valeur de MONGO_URI de ton .env
client = MongoClient("mongodb+srv://zetaagency237:nlBmk8pqXkUFVH0A@brawlbase.glbdxmw.mongodb.net/brawlbase?retryWrites=true&w=majority")
db = client.brawlbase

# Affiche tous les joueurs enregistrés
for player in db.players.find():
    print(player)