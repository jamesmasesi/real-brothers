import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///realbrothers.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = 'static/uploads/profiles'
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # 2MB Limit

    # Group Constants
    GROUP_START_YEAR = 2023
    MONTHLY_CONTRIBUTION = 200
    LATE_FEE = 50
    ABSENT_FEE = 200
    ANNUAL_CONTRIBUTION = 15000
    SUPPORT_PAYOUT = 120000
