# database.py
from motor.motor_asyncio import AsyncIOMotorClient
import os

# সরাসরি একটা URL — Render এ Environment Variable হিসেবে দিবেন
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB", "financial_analyzer")

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

# Collections
companies_collection = db["companies"]
financial_data_collection = db["financial_data"]
analysis_results_collection = db["analysis_results"]

async def init_db():
    """Create indexes"""
    try:
        await companies_collection.create_index("ticker", unique=True)
        await financial_data_collection.create_index(
            [("company_id", 1), ("year", 1), ("quarter", 1)], 
            unique=True
        )
        print("✅ Database connected & indexes created!")
    except Exception as e:
        print(f"⚠️ Index warning: {e}")
