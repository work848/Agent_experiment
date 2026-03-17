from exa_py import Exa
import os
import json
from tools.base_tool import tool
from dotenv import load_dotenv
load_dotenv(dotenv_path="APIKey.env")  # 从 .env 文件加载环境变量
# print(f"Loaded Exa API Key: {os.getenv('EXA_API_KEY')}")
exa = Exa(api_key=os.getenv("EXA_API_KEY"))

@tool
def exa_search(query: str, num_results: int = 5):
    """
    使用 Exa 搜索并返回结构化结果
    """

    results = exa.search_and_contents(
        query,
        type="auto",
        num_results=num_results,
        text={"max_characters": 800}
    )

    output = []

    for r in results.results:
        output.append({
            "title": r.title,
            "url": r.url,
            "content": r.text
        })
    print(f"Exa 搜索到 {len(output)} 条结果")
    return json.dumps(output, ensure_ascii=False)