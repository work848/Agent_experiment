import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv

load_dotenv(dotenv_path="APIKey.env")
from agent.nodes.tool_node import tool_node
import json
# ==========================
# 本地测试
# ==========================

if __name__ == "__main__":

    fake_state = {
        "messages": [
            {"role": "user", "content": "What is CEO of Nvidia?"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": json.dumps({
                                "query": "What is CEO of Nvidia?",
                                "num_results": 3
                            })
                        }
                    }
                ]
            }
        ]
    }

    result = tool_node(fake_state)

    print("\n==== 新状态 ====")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
#     Exa 搜索到 3 条结果
# Executing tool: search

# ==== 新状态 ====
# {
#   "messages": [
#     {
#       "role": "user",
#       "content": "What is CEO of Nvidia?"
#     },
#     {
#       "role": "assistant",
#       "content": null,
#       "tool_calls": [
#         {
#           "id": "call_123",
#           "type": "function",
#           "function": {
#             "name": "search",
#             "arguments": "{\"query\": \"Nvidia revenue\", \"num_results\": 3}"
#           }
#         }
#       ]
#     },
#     {
#       "role": "tool",
#       "tool_call_id": "call_123",
#       "content": "[{\"title\": \"Nvidia: Fiscal 4Q26 and FY26 Financial Results - StorageNewsletter\", \"url\": \"https://www.storagenewsletter.com/2026/03/04/nvidia-fiscal-4q26-and-fy26-financial-results/\", \"content\": \"Nvidia: Fiscal 4Q26 and FY26 Financial Results - StorageNewsletter\\n\\n- Advertise with Us\\n- Contact Us\\n- Editorial Policy\\n- Submit News\\n- About Us\\n\\nCategories -- Navigate -- M&As Start-Ups Systems (RAID, NAS, SAN) Financial Results, Investments and IPOs Market Reports/Research & Certifications Solid State (flash, SSD...), Memory... Hard Disk Drives Tapes Optical, DNA Software People Cloud, Online Backup, SSPs, MSPs Connectivity (switch/HBA/interface) Security Partnership (OEM, Channel, Dist. & Alliance) Customer Wins, Awards Business & Cor\"}, {\"title\": \"NVIDIA Reports Q4'FY2026 Earnings: Data Center and ProViz Drive Revenue Records - ServeTheHome\", \"url\": \"https://www.servethehome.com/nvidia-reports-q4-fy2026-earnings-data-center-and-proviz-drive-revenue-records/\", \"content\": \"NVIDIA Reports Q4'FY2026 Earnings: Data Center and ProViz Drive Revenue Records - ServeTheHome\\n\\nFacebook Linkedin RSS TikTok Twitter Youtube\\n\\nServer\\n\\n- Other Components\\n- Server Chassis\\n- Server Motherboards\\n- [Accelerators](https://www.servethehome.com/c\"}, {\"title\": \"NVIDIA Announces Financial Results for Fourth Quarter and\", \"url\": \"https://www.globenewswire.com/news-release/2026/02/25/3245078/0/en/NVIDIA-Reports-Record-Q4-Revenue-of-68-1-Billion.html\", \"content\": \"NVIDIA Announces Financial Results for Fourth Quarter and --\\n\\n# NVIDIA Announces Financial Results for Fourth Quarter and Fiscal 2026\\n\\nFebruary 25, 2026 16:31 ET | Source: NVIDIA Follow NVIDIA\\n\\n---\\n\\nShare\\n\\n---\\n\\n- Record full-year revenue of $215.9 billion, up 65%\\n- Record quarterly Data Center revenue of $62.3 billion, up 22% from Q3 and up 75% from a year ago\\n- Record quarterly revenue of $68.1 billion, up 20% from Q3 and up 73% from a year ago\\n\\nSANTA CLARA, Calif., Feb. 25, 2026 (GLOBE NEWSWIRE) -- NVIDIA (NASDAQ: NVDA) today reported record revenue for the fourth quarter ended January 25, 2026, of $68.1 billion, up 20% from the previous quarter and up 73% from a year ago. For fiscal 2026, revenue was $215.9 b\"}]"
#     }
#   ],
#   "tool_call": false
# }