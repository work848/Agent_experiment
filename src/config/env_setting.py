import os
from dotenv import load_dotenv

load_dotenv("APIKey.env")

BASE_URL = "https://api.deepseek.com"
BASE_KEY = os.getenv("deepseek")  # 从环境变量中获取 API Key
