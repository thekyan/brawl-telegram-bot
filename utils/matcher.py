# utils/matcher.py
def find_opponent(player_trophies):
    return db.players.find_one({
        "trophies": {"$gte": player_trophies - 50, "$lte": player_trophies + 50},
        "available": True
    }).sort("last_active", -1)