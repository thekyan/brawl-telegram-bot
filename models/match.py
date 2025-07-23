from datetime import datetime
from pymongo import IndexModel, DESCENDING, ASCENDING
from bson import ObjectId
from typing import Dict, List, Optional, Union
import logging
from pymongo.errors import DuplicateKeyError, OperationFailure

logger = logging.getLogger(__name__)

class PlayerModel:
    """Modèle avancé pour la gestion des joueurs Brawl Stars avec validation et gestion des erreurs"""
    
    COLLECTION_NAME = "players"
    MAX_TROPHIES = 50000  # Limite réaliste Brawl Stars
    DEFAULT_WIN_RATE = 0.5  # Valeur par défaut pour les nouveaux joueurs

    def __init__(self, db):
        """
        Initialise le modèle avec une connexion MongoDB
        Args:
            db (Database): Instance pymongo.Database
        """
        self.collection = db[self.COLLECTION_NAME]
        self._ensure_indexes()
        self._validate_schema()

    def _ensure_indexes(self) -> None:
        """Crée les index nécessaires de manière idempotente"""
        index_specs = [
            {'keys': [('telegram_id', ASCENDING)], 'name': 'telegram_id_unique', 'unique': True},
            {'keys': [('trophies', DESCENDING)], 'name': 'trophies_ranking'},
            {'keys': [('last_active', DESCENDING)], 'name': 'activity_tracking'},
            {'keys': [('username', 'text')], 'name': 'username_search'}
        ]
        
        try:
            # Création atomique des index
            self.collection.create_indexes([IndexModel(**spec) for spec in index_specs])
        except OperationFailure as e:
            logger.error(f"Échec création index: {e.details}")
            raise

    def _validate_schema(self) -> None:
        """Valide que la collection correspond au schéma attendu"""
        sample_doc = {
            "telegram_id": 1234567890,
            "username": "test_user",
            "trophies": 0,
            "brawlers": [{"name": "Shelly", "power_level": 1}],
            "matches_played": 0,
            "win_rate": self.DEFAULT_WIN_RATE,
            "last_active": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }
        try:
            self.collection.insert_one(sample_doc)
            self.collection.delete_one({"telegram_id": 1234567890})
        except Exception as e:
            logger.critical(f"Schéma invalide: {e}")
            raise

    def create_player(self, telegram_id: int, username: str) -> ObjectId:
        """
        Crée un nouveau joueur avec validation complète
        Args:
            telegram_id: ID Telegram unique (positif)
            username: Nom d'utilisateur (3-32 caractères)
        Returns:
            ObjectId: ID MongoDB du joueur créé
        Raises:
            ValueError: Si les données sont invalides
            DuplicateKeyError: Si le joueur existe déjà
        """
        if not isinstance(telegram_id, int) or telegram_id <= 0:
            raise ValueError("ID Telegram doit être un entier positif")

        player_data = {
            "telegram_id": telegram_id,
            "username": username.strip(),
            "trophies": 0,
            "brawlers": [],
            "matches_played": 0,
            "win_rate": self.DEFAULT_WIN_RATE,
            "last_active": datetime.utcnow(),
            "created_at": datetime.utcnow()
        }

        try:
            result = self.collection.insert_one(player_data)
            logger.info(f"Nouveau joueur: {telegram_id}")
            return result.inserted_id
        except DuplicateKeyError:
            logger.warning(f"Joueur existe déjà: {telegram_id}")
            raise
        except Exception as e:
            logger.error(f"Erreur création joueur: {e}")
            raise OperationFailure("Échec création joueur")

    def update_stats(
        self,
        telegram_id: int,
        trophies_delta: int = 0,
        matches_played: int = 0,
        wins: int = 0
    ) -> bool:
        """
        Met à jour les statistiques du joueur de manière atomique
        Args:
            telegram_id: ID Telegram du joueur
            trophies_delta: Variation des trophées
            matches_played: Parties jouées à ajouter
            wins: Victoires à ajouter
        Returns:
            bool: True si mise à jour réussie
        """
        update = {
            "$inc": {
                "trophies": trophies_delta,
                "matches_played": matches_played,
                "wins": wins
            },
            "$set": {"last_active": datetime.utcnow()},
            "$max": {"trophies": 0},  # Empêche les valeurs négatives
            "$min": {"trophies": self.MAX_TROPHIES}
        }

        try:
            result = self.collection.update_one(
                {"telegram_id": telegram_id},
                update
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Erreur MAJ stats {telegram_id}: {e}")
            return False

    def get_leaderboard(self, limit: int = 10, min_matches: int = 5) -> List[Dict]:
        """
        Récupère le classement des joueurs actifs
        Args:
            limit: Nombre maximum de résultats
            min_matches: Filtre les joueurs inactifs
        Returns:
            List: Joueurs triés par trophées
        """
        pipeline = [
            {"$match": {
                "matches_played": {"$gte": min_matches},
                "trophies": {"$gt": 0}
            }},
            {"$project": {
                "username": 1,
                "trophies": 1,
                "win_rate": {
                    "$cond": [
                        {"$eq": ["$matches_played", 0]},
                        0,
                        {"$divide": ["$wins", "$matches_played"]}
                    ]
                },
                "activity_ratio": {
                    "$divide": [
                        {"$subtract": [datetime.utcnow(), "$last_active"]},
                        3600000  # Heures depuis dernière activité
                    ]
                }
            }},
            {"$sort": {"trophies": DESCENDING}},
            {"$limit": limit}
        ]

        try:
            return list(self.collection.aggregate(pipeline))
        except Exception as e:
            logger.error(f"Erreur classement: {e}")
            return []

    def get_player(self, telegram_id: int) -> Optional[Dict]:
        """Récupère un joueur par son ID Telegram"""
        try:
            return self.collection.find_one(
                {"telegram_id": telegram_id},
                {"_id": 0, "username": 1, "trophies": 1, "brawlers": 1}
            )
        except Exception as e:
            logger.error(f"Erreur récupération joueur {telegram_id}: {e}")
            return None