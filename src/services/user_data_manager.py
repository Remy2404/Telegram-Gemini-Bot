from pymongo.collection import Collection
from datetime import datetime, timedelta
from typing import Dict, List, Any
import logging

class UserDataManager:
    def __init__(self, db):
        """
        Initialize UserDataManager with a database connection.
        
        :param db: MongoDB database instance
        """
        self.db = db
        self.users_collection: Collection = self.db.users
        self.logger = logging.getLogger(__name__)

    def initialize_user(self, user_id: str) -> List[str]:
        """
        Initialize a new user in the database.
        
        :param user_id: Unique identifier for the user
        """
        try:
            self.users_collection.insert_one({
                "user_id": user_id,
                "contexts": [],
                "settings": {
                    "language": "en",
                    "notifications": True
                },
                "stats": {
                    "messages": 0,
                    "voice_messages": 0,
                    "images": 0,
                    "last_active": datetime.now().isoformat()
                }
            })
            self.logger.info(f"Initialized new user: {user_id}")
        except Exception as e:
            self.logger.error(f"Error initializing user {user_id}: {str(e)}")
            raise
        user_data = self.get_user_data(user_id)
        return user_data.get("contexts", [])

    def clear_history(self, user_id: str) -> None:
        """
        Clear the conversation history for a user.
        
        :param user_id: Unique identifier for the user
        """
        try:
            self.users_collection.update_one(
                {"user_id": user_id}, 
                {"$set": {"contexts": []}}
            )
            self.logger.info(f"Cleared history for user: {user_id}")
        except Exception as e:
            self.logger.error(f"Error clearing history for user {user_id}: {str(e)}")
            raise

    def add_message(self, user_id: str, message: str) -> None:
        """
        Add a message to the user's conversation history.
        
        :param user_id: Unique identifier for the user
        :param message: Message to be added to the history
        """
        try:
            self.users_collection.update_one(
                {"user_id": user_id},
                {"$push": {"contexts": message}}
            )
            self.logger.debug(f"Added message to history for user: {user_id}")
        except Exception as e:
            self.logger.error(f"Error adding message for user {user_id}: {str(e)}")
            raise

    def get_user_data(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve all data for a specific user.
        
        :param user_id: Unique identifier for the user
        :return: Dictionary containing user data
        """
        try:
            user_data = self.users_collection.find_one({"user_id": user_id})
            if not user_data:
                self.initialize_user(user_id)
                user_data = self.users_collection.find_one({"user_id": user_id})
            return user_data
        except Exception as e:
            self.logger.error(f"Error retrieving data for user {user_id}: {str(e)}")
            raise

    def get_user_context(self, user_id: str) -> List[str]:
        """
        Retrieve the context for a specific user.
        
        :param user_id: Unique identifier for the user
        :return: List of context messages for the user
        """
        user_data = self.get_user_data(user_id)
        return user_data.get("contexts", [])

    def get_conversation_history(self, user_id: str) -> List[str]:
        """
        Retrieve the conversation history for a user.
        
        :param user_id: Unique identifier for the user
        :return: List of conversation context messages
        """
        user_data = self.get_user_data(user_id)
        return user_data.get("contexts", [])

    def update_stats(self, user_id: str, text_message: bool = False, voice_message: bool = False, image: bool = False) -> None:
        """
        Update user statistics based on their activity.
        
        :param user_id: Unique identifier for the user
        :param text_message: Whether a text message was sent
        :param voice_message: Whether a voice message was sent
        :param image: Whether an image was sent
        """
        try:
            user = self.get_user_data(user_id)
            stats = user['stats']
            stats['last_active'] = datetime.now().isoformat()
            
            if text_message:
                stats['messages'] += 1
            if voice_message:
                stats['voice_messages'] += 1
            if image:
                stats['images'] += 1
            
            self.users_collection.update_one(
                {"user_id": user_id}, 
                {"$set": {"stats": stats}}
            )
            self.logger.debug(f"Updated stats for user: {user_id}")
        except Exception as e:
            self.logger.error(f"Error updating stats for user {user_id}: {str(e)}")
            raise

    def get_user_settings(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve user settings.
        
        :param user_id: Unique identifier for the user
        :return: Dictionary of user settings
        """
        user_data = self.get_user_data(user_id)
        return user_data.get('settings', {})

    def update_user_settings(self, user_id: str, new_settings: Dict[str, Any]) -> None:
        """
        Update user settings.
        
        :param user_id: Unique identifier for the user
        :param new_settings: Dictionary of settings to update
        """
        try:
            current_settings = self.get_user_settings(user_id)
            current_settings.update(new_settings)
            self.users_collection.update_one(
                {"user_id": user_id},
                {"$set": {"settings": current_settings}}
            )
            self.logger.info(f"Updated settings for user: {user_id}")
        except Exception as e:
            self.logger.error(f"Error updating settings for user {user_id}: {str(e)}")
            raise

    def cleanup_inactive_users(self, days_threshold: int = 30) -> None:
        """
        Remove data for inactive users.
        
        :param days_threshold: Number of days of inactivity before cleanup
        """
        try:
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            result = self.users_collection.delete_many(
                {"stats.last_active": {"$lt": threshold_date.isoformat()}}
            )
            self.logger.info(f"Cleaned up {result.deleted_count} inactive users")
        except Exception as e:
            self.logger.error(f"Error during cleanup of inactive users: {str(e)}")
            raise

    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """
        Retrieve user statistics.
        
        :param user_id: Unique identifier for the user
        :return: Dictionary of user statistics
        """
        user_data = self.get_user_data(user_id)
        return user_data.get('stats', {})