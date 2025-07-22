from datetime import datetime
from pymongo import IndexModel

class Match:
    def __init__(self):
        self.schema = {
            'players': [
                {
                    'telegram_id': int,
                    'brawler': str,
                    'trophies': int,
                    'team': str
                }
            ],
            'status': {'type': str, 'default': 'pending'},
            'created_at': {'type': datetime, 'default': datetime.utcnow}
        }

        self.indexes = [
            IndexModel([('status', 1)]),
            IndexModel([('players.telegram_id', 1)])
        ]