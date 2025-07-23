from pymongo import MongoClient
from models.players import Player
from models.match import Match
from models.tournament import Tournament

client = MongoClient(os.getenv("MONGO_URI"))
db = client.brawl_stars_prod  # Ou brawl_stars_dev

# Initialisation
players_model = Player(db)
matches_model = Match(db)
tournaments_model = Tournament(db)