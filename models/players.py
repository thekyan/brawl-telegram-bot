from datetime import datetime
from pymongo import IndexModel, DESCENDING
from bson import ObjectId
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class Player:
    """Modèle pour la gestion des joueurs Brawl Stars avec validation avancée"""
    
    COLLECTION_NAME = "players"
    MAX_TROPHIES = 50000  # Limite réaliste

    def __init__(self, db):
        """
        Initialise le modèle joueur
        :param db: Instance pymongo.Database
        """
        self.collection = db[self.COLLECTION_NAME]
        self.teams_collection = db["teams"]
        self._create_indexes()
    
    def _create_indexes(self) -> None:
        """Crée les index optimisés pour les requêtes fréquentes"""
        try:
            indexes = [
                IndexModel([("telegram_id", 1)], unique=True, name="telegram_id_unique"),
                IndexModel([("trophies", DESCENDING)], name="trophies_desc"),
                IndexModel([("last_active", DESCENDING)], name="last_active_desc"),
                IndexModel([("username", "text")], name="username_text_search"),
                IndexModel([("team_id", 1)], name="team_id_index")
            ]
            self.collection.create_indexes(indexes)
        except Exception as e:
            logger.critical(f"Erreur création index: {e}")
            raise

    @property
    def schema(self) -> Dict:
        """Schéma de validation complet avec règles métier"""
        return {
            "telegram_id": {
                "type": int,
                "required": True,
                "min": 1  # Les IDs Telegram sont positifs
            },
            "username": {
                "type": str,
                "minlength": 3,
                "maxlength": 32,
                "regex": r"^[a-zA-Z0-9_]+$"  # Format standard Telegram
            },
            "trophies": {
                "type": int,
                "default": 0,
                "min": 0,
                "max": self.MAX_TROPHIES
            },
            "brawlers": {
                "type": list,
                "default": [],
                "schema": {
                    "type": dict,
                    "schema": {
                        "name": {"type": str, "required": True},
                        "power_level": {"type": int, "min": 1, "max": 11},
                        "last_used": {"type": datetime}
                    }
                }
            },
            "matches_played": {"type": int, "default": 0, "min": 0},
            "win_rate": {
                "type": float,
                "default": 0.0,
                "min": 0.0,
                "max": 1.0
            },
            "team_id": {
                "type": ObjectId,
                "default": None
            },
            "last_active": {"type": datetime, "default": datetime.utcnow},
            "created_at": {"type": datetime, "default": datetime.utcnow}
        }

    def create_player(self, telegram_id: int, username: str) -> ObjectId:
        """
        Crée un nouveau joueur avec validation
        :param telegram_id: ID Telegram unique
        :param username: Nom d'utilisateur
        :return: ID du joueur créé
        :raises: pymongo.errors.DuplicateKeyError si le joueur existe déjà
        """
        player_data = {
            "telegram_id": telegram_id,
            "username": username,
            **{k: v["default"] for k, v in self.schema.items() if "default" in v}
        }
        
        try:
            result = self.collection.insert_one(player_data)
            logger.info(f"Joueur créé: {telegram_id}")
            return result.inserted_id
        except Exception as e:
            logger.error(f"Erreur création joueur {telegram_id}: {e}")
            raise

    def update_trophies(self, telegram_id: int, delta: int) -> bool:
        """
        Met à jour les trophées de manière atomique
        :param telegram_id: ID Telegram
        :param delta: Variation (+/-)
        :return: True si mis à jour
        """
        try:
            result = self.collection.update_one(
                {"telegram_id": telegram_id},
                {
                    "$inc": {"trophies": delta},
                    "$set": {"last_active": datetime.utcnow()},
                    "$min": {"trophies": self.MAX_TROPHIES}  # Plafonnement
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Erreur MAJ trophées {telegram_id}: {e}")
            return False

    def get_leaderboard(self, limit: int = 10) -> List[Dict]:
        """
        Récupère le classement des joueurs
        :param limit: Nombre de joueurs à retourner
        :return: Liste des joueurs triés
        """
        try:
            return list(self.collection.find(
                {"trophies": {"$gt": 0}},  # Exclut les joueurs à 0 trophées
                {"username": 1, "trophies": 1, "win_rate": 1, "_id": 0}
            ).sort("trophies", DESCENDING).limit(limit))
        except Exception as e:
            logger.error(f"Erreur récupération classement: {e}")
            return []

    # --- Gestion des teams ---

    def set_team(self, telegram_id: int, team_id: ObjectId) -> bool:
        """
        Associe un joueur à une team (ou None pour retirer)
        :param telegram_id: ID Telegram du joueur
        :param team_id: ObjectId de la team ou None
        :return: True si modifié
        """
        try:
            result = self.collection.update_one(
                {"telegram_id": telegram_id},
                {"$set": {"team_id": team_id}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Erreur set_team {telegram_id}: {e}")
            return False

    def get_team(self, telegram_id: int) -> Optional[Dict]:
        """
        Récupère la team du joueur (ou None)
        :param telegram_id: ID Telegram du joueur
        :return: Dictionnaire team ou None
        """
        player = self.collection.find_one({"telegram_id": telegram_id})
        if player and player.get("team_id"):
            return self.teams_collection.find_one({"_id": player["team_id"]})
        return None

    def remove_from_team(self, telegram_id: int) -> bool:
        """
        Retire le joueur de sa team
        :param telegram_id: ID Telegram du joueur
        :return: True si modifié
        """
        return self.set_team(telegram_id, None)