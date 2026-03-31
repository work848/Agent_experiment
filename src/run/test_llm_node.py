import json
import sys
import os
from dotenv import load_dotenv

load_dotenv(dotenv_path="APIKey.env")
# 把 src 目录加入到搜索路径中
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from llm.llm_requirements_client import call_gpt_requirements
from agent.nodes.chat_node import RequirementExtractionOutput
schema = json.dumps(RequirementExtractionOutput.model_json_schema(), ensure_ascii=False, indent=2)
state = {
    "messages": [
        {"role":"system", "content": f"""you are an expert requirement analysis product requirements from conversation.
        Return only JSON, matching this schema exactly:
        {schema}

        if you cant output json format, the output i cant do it
        Rules:
        - Return normalized requirements without IDs.
        - title should be concise.
        - description should be specific and actionable.
        - acceptance_criteria should be concrete and testable.
        - priority range is 1 (highest) to 5 (lowest)."""},
        {"role": "user", "content": "你好，我想要制作一个日语学习app，但是有ai功能，ai可以根据用户学习进度来进行安排复习和练习我主要面对完全零基础的人群，这个app的主要目的是为了帮助外国人在日本找工作的实用类。2.五十音，词汇、语法、听力、会话 都有。是综合类app 3.ai的作用是根据用户目前学习进度来制作练习语法，词汇类练习，练习的类型根据用户的正确率和学习进度来。4复习时间采用艾宾浩斯遗忘曲线 5.我自己学习日语时最大的问题是难以得到我想要的练习方式，我希望ai可以定制复习或者练习需要加强职场相关的内容，面试，简历，和职业相关单词，但是这些要等用户把基础打好才可以进行专项训练，2.如果用户某一个知识点一直错误的话，我更倾向于使用情景会话的方式来帮助用户理解 3.练习方便以翻译题为主，选择题为辅助的模式，外加一定阶段后的情景对话模拟。4.我们这个app是注重职业训练所以，用户需要先表达自己的就业倾向，之后给对应的推荐路线。基础路线五十音→基础词汇→N5语法所有路线都是固定，之后随着职业不同来改变"}
    ]
}
state1 = [{
    "role": "user", "content":"hello"   
}]

result = call_gpt_requirements(state1)

print(json.dumps(result, indent=4, ensure_ascii=False))