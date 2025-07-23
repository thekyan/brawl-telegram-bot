from datetime import datetime
from pymongo import IndexModel, ASCENDING, DESCENDING
from bson import ObjectId
from typing import Dict, List, Optional
import logging
from enum import Enum, auto
from pymongo.errors import OperationFailure, DuplicateKeyError

logger = logging.getLogger(__name__)

class TournamentStatus(Enum):
    UPCOMING = auto()
    REGISTRATION = auto()
    ONGOING = auto()
    COMPLETED = auto()
    CANCELLED = auto()

class Tournament:
    """Modèle avancé pour la gestion des tournois Brawl Stars avec système de brackets"""

    COLLECTION_NAME = "tournaments"
    MAX_TEAMS = 128  # Limite réaliste
    MIN_TEAMS = 2    # Minimum pour démarrer

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
            {'keys': [('status', ASCENDING)], 'name': 'status_index'},
            {'keys': [('start_date', DESCENDING)], 'name': 'start_date_index'},
            {'keys': [('name', 'text')], 'name': 'name_text_search'},
            {'keys': [('teams.players', ASCENDING)], 'name': 'players_lookup'}
        ]
        
        try:
            self.collection.create_indexes([IndexModel(**spec) for spec in index_specs])
        except OperationFailure as e:
            logger.error(f"Échec création index: {e.details}")
            raise

    def _validate_schema(self) -> None:
        """Valide que la collection correspond au schéma attendu"""
        sample_tournament = {
            "name": "Test Tournament",
            "mode": "3v3",
            "status": TournamentStatus.UPCOMING.name,
            "teams": [{
                "name": "Test Team",
                "players": [123456789],
                "wins": 0,
                "losses": 0
            }],
            "created_at": datetime.utcnow()
        }
        try:
            self.collection.insert_one(sample_tournament)
            self.collection.delete_one({"name": "Test Tournament"})
        except Exception as e:
            logger.critical(f"Schéma invalide: {e}")
            raise

    def create_tournament(
        self,
        name: str,
        mode: str,
        max_teams: int,
        prize_pool: str = ""
    ) -> ObjectId:
        """
        Crée un nouveau tournoi avec validation
        Args:
            name: Nom du tournoi
            mode: Format de jeu (1v1, 2v2, 3v3)
            max_teams: Nombre maximum d'équipes
            prize_pool: Description des récompenses
        Returns:
            ObjectId: ID du tournoi créé
        Raises:
            ValueError: Si les paramètres sont invalides
        """
        if mode not in ["1v1", "2v2", "3v3"]:
            raise ValueError("Mode de jeu invalide")
        if not (self.MIN_TEAMS <= max_teams <= self.MAX_TEAMS):
            raise ValueError(f"Nombre d'équipes doit être entre {self.MIN_TEAMS} et {self.MAX_TEAMS}")

        tournament_data = {
            "name": name.strip(),
            "mode": mode,
            "max_teams": max_teams,
            "prize_pool": prize_pool,
            "status": TournamentStatus.UPCOMING.name,
            "teams": [],
            "brackets": {},
            "created_at": datetime.utcnow(),
            "started_at": None,
            "ended_at": None
        }

        try:
            result = self.collection.insert_one(tournament_data)
            logger.info(f"Tournoi créé: {name}")
            return result.inserted_id
        except DuplicateKeyError:
            logger.warning(f"Tournoi existe déjà: {name}")
            raise
        except Exception as e:
            logger.error(f"Erreur création tournoi: {e}")
            raise OperationFailure("Échec création tournoi")

    def register_team(
        self,
        tournament_id: ObjectId,
        team_name: str,
        players: List[int],
        captain_id: int
    ) -> bool:
        """
        Enregistre une équipe dans un tournoi
        Args:
            tournament_id: ID du tournoi
            team_name: Nom de l'équipe
            players: Liste des IDs Telegram des joueurs
            captain_id: ID du capitaine
        Returns:
            bool: True si l'inscription a réussi
        """
        if not players or captain_id not in players:
            raise ValueError("Le capitaine doit faire partie de l'équipe")

        team_data = {
            "name": team_name.strip(),
            "players": players,
            "captain": captain_id,
            "wins": 0,
            "losses": 0,
            "registered_at": datetime.utcnow()
        }

        try:
            result = self.collection.update_one(
                {
                    "_id": tournament_id,
                    "status": TournamentStatus.UPCOMING.name,
                    "$where": f"this.teams.length < this.max_teams"
                },
                {"$push": {"teams": team_data}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Erreur inscription équipe: {e}")
            return False

    def start_tournament(self, tournament_id: ObjectId) -> bool:
        """
        Démarre un tournoi et génère les brackets
        Args:
            tournament_id: ID du tournoi
        Returns:
            bool: True si le tournoi a démarré
        """
        try:
            # Vérifier qu'il y a assez d'équipes
            tournament = self.collection.find_one({"_id": tournament_id})
            if len(tournament["teams"]) < self.MIN_TEAMS:
                raise ValueError(f"Minimum {self.MIN_TEAMS} équipes requis")

            # Générer les brackets (simplifié)
            brackets = self._generate_brackets(tournament["teams"])
            
            result = self.collection.update_one(
                {"_id": tournament_id},
                {
                    "$set": {
                        "status": TournamentStatus.ONGOING.name,
                        "brackets": brackets,
                        "started_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Erreur démarrage tournoi: {e}")
            return False

    def _generate_brackets(self, teams: List[Dict]) -> Dict:
        """Génère la structure initiale des brackets"""
        return {
            "type": "single_elimination",
            "rounds": [
                {
                    "name": "Quarts de finale",
                    "matches": []  # À remplir avec la logique réelle
                }
            ]
        }

    def get_active_tournaments(self) -> List[Dict]:
        """Récupère les tournois en cours d'inscription ou en cours"""
        try:
            return list(self.collection.find(
                {
                    "status": {
                        "$in": [
                            TournamentStatus.UPCOMING.name,
                            TournamentStatus.ONGOING.name
                        ]
                    }
                },
                {
                    "name": 1,
                    "mode": 1,
                    "status": 1,
                    "teams_count": {"$size": "$teams"},
                    "max_teams": 1
                }
            ))
        except Exception as e:
            logger.error(f"Erreur récupération tournois: {e}")
            return []