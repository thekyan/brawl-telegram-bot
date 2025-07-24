from pymongo import MongoClient
from bson import ObjectId
import os

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "brawlbase")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

def create_team(name, creator_id, player_ids=None):
    """
    Crée une équipe avec un nom, un créateur et une liste d'IDs de joueurs (optionnel).
    Vérifie qu'aucun joueur n'est déjà dans une autre équipe.
    """
    if player_ids is None:
        player_ids = []

    # Vérifie qu'aucun joueur n'a déjà une team
    existing = db.players.find({"_id": {"$in": [ObjectId(pid) for pid in player_ids]}, "team_id": {"$ne": None}})
    if existing.count() > 0:
        raise Exception("Un ou plusieurs joueurs sont déjà dans une équipe.")

    team = {
        "name": name,
        "creator_id": creator_id,
        "player_ids": [ObjectId(pid) for pid in player_ids]
    }
    team_id = db.teams.insert_one(team).inserted_id

    # Mets à jour chaque player pour lui associer la team
    if player_ids:
        db.players.update_many(
            {"_id": {"$in": [ObjectId(pid) for pid in player_ids]}},
            {"$set": {"team_id": team_id}}
        )
    return team_id

def add_player_to_team(team_id, player_id):
    """
    Ajoute un joueur à une équipe si il n'a pas déjà une team.
    """
    player = db.players.find_one({"_id": ObjectId(player_id)})
    if player.get("team_id"):
        raise Exception("Ce joueur est déjà dans une équipe.")
    db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$addToSet": {"player_ids": ObjectId(player_id)}}
    )
    db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"team_id": ObjectId(team_id)}}
    )

def remove_player_from_team(team_id, player_id):
    """
    Retire un joueur d'une équipe.
    """
    db.teams.update_one(
        {"_id": ObjectId(team_id)},
        {"$pull": {"player_ids": ObjectId(player_id)}}
    )
    db.players.update_one(
        {"_id": ObjectId(player_id)},
        {"$set": {"team_id": None}}
    )

def get_team(team_id):
    return db.teams.find_one({"_id": ObjectId(team_id)})

def get_player_team(player_id):
    player = db.players.find_one({"_id": ObjectId(player_id)})
    if player:
        return player.get("team_id")
    return None

def list_teams():
    return list(db.teams.find())