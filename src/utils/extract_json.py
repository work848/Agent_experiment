import json
import re
def extract_json(text):
    
    match = re.search(r"\{.*\}", text, re.S)

    if not match:
        raise ValueError("No JSON found")

    json_text = match.group()

    # 验证 JSON
    try:
        json.loads(json_text)
    except json.JSONDecodeError as e:
        print("Invalid JSON from LLM:")
        print(json_text)
        raise e

    return json_text