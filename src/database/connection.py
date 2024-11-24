import os
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get MongoDB connection string from environment variable
MONGODB_URI = os.getenv('DATABASE_URL')

def get_database():
    """
    Establishes a connection to the MongoDB database.

    Returns:
        db (Database): The MongoDB database instance.
        client (MongoClient): The MongoDB client instance.
    """
    if not MONGODB_URI:
        logger.error("DATABASE_URL environment variable is not set")
        return None, None

    try:
        # Create a new client and connect to the server
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        
        # Send a ping to confirm a successful connection
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB!")

        # Get the database
        db_name = os.getenv('MONGODB_DB_NAME', 'gembot')  # Use environment variable or default to 'gembot'
        db = client[db_name]
        return db, client
    except ConnectionFailure as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        return None, None
    except Exception as e:
        logger.error(f"An unexpected error occurred while connecting to MongoDB: {e}")
        return None, None

def close_database_connection(client):
    """
    Closes the MongoDB client connection.

    Args:
        client (MongoClient): The MongoDB client instance to close.
    """
    if client:
        try:
            client.close()
            logger.info("MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")