import os
from dotenv import load_dotenv

from langchain_openai import OpenAIEmbeddings


load_dotenv(dotenv_path="APIKey.env")


def get_embedding_model():
    key = os.getenv("OPENAI_API_KEY")

    return OpenAIEmbeddings(
        model="Pro/BAAI/bge-m3",
        api_key=key,
        openai_api_base="https://api.siliconflow.cn/v1",
        chunk_size=64
    )