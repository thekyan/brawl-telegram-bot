from pymongo import MongoClient
from pymongo.errors import PyMongoError

class MongoDB:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.client = MongoClient(
                os.getenv('MONGO_URI'),
                serverSelectionTimeoutMS=5000,
                maxPoolSize=50,
                connect=False
            )
            cls._instance.db = cls._instance.client.get_database()
        return cls._instance

    def get_users_collection(self):
        return self.db.users.create_index([('telegram_id', 1)], unique=True)
    
    