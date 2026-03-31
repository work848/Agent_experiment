# Error Node 测试指导

这份文档用于日常验证 error node 的自动重试行为。

相关测试文件：
- `tests/test_planner_node.py`
- `tests/test_error_flow.py`

相关实现文件：
- `src/agent/nodes/error_node.py`
- `src/agent/nodes/coordinator_node.py`
- `src/agent/nodes/planner_node.py`
- `src/agent/nodes/interface_build_node.py`
- `src/api/main.py`

---

## 1. 运行命令

如果环境已安装 pytest：

```bash
python -m pytest "tests/test_planner_node.py" "tests/test_error_flow.py"
```

如果环境未安装 pytest：

```bash
pip install pytest
python -m pytest "tests/test_planner_node.py" "tests/test_error_flow.py"
```

---

## 2. 重点验证目标

### A. coordinator 能路由到 error node
对应测试：
- `tests/test_error_flow.py`
- `test_coordinator_routes_to_error_node`

预期：
- 当 `next_node = NextNode.ERROR` 时
- `central_coordinator(state)` 返回 `"error"`

---

### B. error node 在首次失败后会提示“正在自动重试”
对应测试：
- `tests/test_error_flow.py`
- `test_error_node_announces_retry_for_planner`

预期：
- `next_node == NextNode.PLANNER`
- `trigger_plan is True`
- `retry_count == 1`
- `retrying_node == "planner"`
- 返回消息中包含：`正在自动重试 1/1`

---

### C. error node 超过重试预算后返回最终失败消息
对应测试：
- `tests/test_error_flow.py`
- `test_error_node_returns_final_message_after_retry_budget`

预期：
- `next_node == NextNode.END`
- `retrying_node is None`
- 最后一条 assistant 消息包含：`已自动重试一次，但仍未成功`

---

### D. planner 首次失败后自动重试一次，再成功
对应测试：
- `tests/test_error_flow.py`
- `test_graph_retries_planner_once`

预期：
- planner 调用 2 次
- 第 1 次非法 JSON
- 第 2 次合法 JSON
- 最终 `plan` 成功生成
- `plan[0].interface is not None`
- `messages` 中出现：`正在自动重试 1/1`

---

### E. interface 连续失败两次后停止
对应测试：
- `tests/test_error_flow.py`
- `test_graph_stops_after_interface_retry_exhausted`

预期：
- `next_node == NextNode.END`
- `retrying_node is None`
- `retry_count == 1`
- 最后一条 assistant 消息包含：`已自动重试一次，但仍未成功`

---

### F. planner 节点失败时不直接结束，而是转到 error node
对应测试：
- `tests/test_planner_node.py`
- `test_planner_node_routes_to_error_on_invalid_json`

预期：
- `current_agent == NextNode.PLANNER`
- `last_failed_node == NextNode.PLANNER`
- `next_node == NextNode.ERROR`
- `last_error_message == "规划节点（planner）生成失败。"`
- `progress_text == "当前进度：需求已整理，等待重新生成开发计划。"`

---

## 3. 手工接口联调检查

启动后端后，调用 `/chat` 或 `/state`，重点检查以下字段：

- `last_error_message`
- `retry_count`
- `retrying_node`
- `progress_text`

### 首次失败并进入自动重试时
预期类似：

```json
{
  "last_error_message": "规划节点（planner）生成失败。",
  "retry_count": 1,
  "retrying_node": "planner",
  "progress_text": "当前进度：需求已整理，正在重新生成开发计划。"
}
```

### 自动重试成功后
预期类似：

```json
{
  "last_error_message": null,
  "retry_count": 0,
  "retrying_node": null,
  "progress_text": "当前进度：开发计划已生成，正在补全接口定义。"
}
```

### 自动重试后仍失败
预期类似：

```json
{
  "last_error_message": "接口节点（interface）生成失败。",
  "retry_count": 1,
  "retrying_node": null,
  "progress_text": "当前进度停留在接口定义补全阶段。"
}
```

---

## 4. 失败时请反馈给 Claude 的信息

如果测试失败，请把下面内容贴出来：

1. pytest 报错全文
2. 失败的测试名
3. 你本次修改过的相关 diff
4. 如果是接口联调失败，再补：
   - `/chat` 的请求 payload
   - 实际 response JSON

---

## 5. 日常最小验证清单

每天至少检查：

- [ ] `test_coordinator_routes_to_error_node`
- [ ] `test_error_node_announces_retry_for_planner`
- [ ] `test_error_node_returns_final_message_after_retry_budget`
- [ ] `test_graph_retries_planner_once`
- [ ] `test_graph_stops_after_interface_retry_exhausted`
- [ ] `test_planner_node_routes_to_error_on_invalid_json`

如果这些都通过，说明 error node 的核心重试链路基本正常。
