# Chat API 文档（多功能编排版）

> 基础地址：`http://localhost:8000`

该 API 统一承担：
- 需求对话（chat）
- 自动进入规划（planner）
- 接口设计补全（interface）
- 计划保存/再生成（通过 `last_user_action`）
- 会话状态持久化（`current_state.json`）

---

## 1. 健康检查

### `GET /`
返回服务状态。

**Response**
```json
{
  "status": "Agent running"
}
```

---

## 2. 主入口

### `POST /chat`
统一入口，按请求内容和会话状态驱动不同流程。

---

## 3. Request 参数

```json
{
  "session_id": "string, 必填",
  "message": "string | string[]，可选",
  "plan": "Step[]，可选（前端编辑后回传）",
  "trigger_plan": "boolean，可选，默认 false",
  "interface_refresh": "boolean，可选，默认 false",
  "last_user_action": "save_plan | regenerate_plan | go_interface | generate_plan | continue_chat | modify_plan，可选",
  "next_node": "chat | planner | interface | coder | END，可选",
  "mode": "chat | planning | executing，可选，默认 chat"
}
```

### 字段说明
- `session_id`：会话主键。同一会话必须复用同一 id。
- `message`：用户输入；若为数组会按换行拼接。
- `plan`：前端改过的 plan/interface。传入后会**先覆盖会话中的 plan**。
- `last_user_action`：用户动作（边沿触发，避免重复执行）。
- `workspace_root`：工作区根目录。首次请求必须传，或由后端环境变量 `WORKSPACE_ROOT` 提供。
- 其他字段通常由系统内部流转使用，前端一般不用频繁手动控制。

---

## 4. Response 结构

```json
{
  "plan": [
    {
      "id": 1,
      "description": "...",
      "implementation_file": "...",
      "status": "pending|running|failed|done",
      "interface": {
        "name": "...",
        "parameters": [{"name": "...", "type": "..."}],
        "return_type": "...",
        "description": "...",
        "dependencies": [1]
      }
    }
  ],
  "current_step": 0,
  "agents": {
    "planner": "idle|working",
    "coder": "idle|working",
    "tester": "idle|working"
  },
  "logs": ["..."],
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "ready_for_plan": true,
  "actions": [
    {"action": "generate_plan", "label": "生成计划"},
    {"action": "continue_chat", "label": "继续补充"}
  ],
  "last_error_message": "规划节点（planner）生成失败。",
  "retry_count": 1,
  "retrying_node": "planner",
  "progress_text": "当前进度：需求已整理，正在重新生成开发计划。"
}
```

### 新增重试/进度字段说明
- `last_error_message`：最近一次失败节点的错误摘要；无错误时为 `null`。
- `retry_count`：当前节点已自动重试次数。成功后会重置为 `0`。
- `retrying_node`：当前正在自动重试的节点名，可能为 `planner` / `interface`；无重试时为 `null`。
- `progress_text`：可直接展示给用户的当前工作进度文案。

### 字段返回时机
- `planner` / `interface` 首次失败后：
  - `retry_count=1`
  - `retrying_node` 为失败节点名
  - `progress_text` 描述当前正在自动重试的阶段
  - `messages` 末尾会追加“正在自动重试 1/1”提示
- 重试成功后：
  - `retrying_node=null`
  - `last_error_message=null`
  - `retry_count=0`
  - `progress_text` 更新为当前成功推进到的阶段
- 重试仍失败后：
  - `retrying_node=null`
  - `last_error_message` 保留最后一次失败摘要
  - `retry_count` 保持已使用次数
  - `messages` 末尾会追加最终失败提示

---

## 5. 核心流程

### A. 普通对话（信息不足）
1. 前端发送 `message`
2. 后端在 chat 模式回复澄清问题
3. `ready_for_plan=false`，`plan` 为空或旧值

### B. 自动规划（先提示，下一次请求自动进 planner）
1. 当 chat 判断需求足够：本次返回提示文案 + `ready_for_plan=true`
2. 下一次请求：自动切到 planning，触发 planner 生成步骤
3. planner 完成后会触发 interface 补全接口定义
4. 最终 `plan`（含 step + interface）返回前端

### C. 用户手工改计划并保存
1. 前端编辑 step/interface
2. 调用 `/chat` 传入：
   - `plan`: 编辑后的完整 plan
   - `last_user_action`: `save_plan`
3. 后端将新 plan 写入会话并保存到 `current_state.json`

### D. 用户要求 AI 改进计划
1. 前端发送修改诉求 `message`
2. 调用 `/chat` 并传 `last_user_action=modify_plan`
3. 进入 planner 再生成（保留增量更新逻辑），随后 interface 刷新
4. 返回更新后的 plan

---

## 6. `last_user_action` 语义

- `save_plan`：保存当前会话状态到 `src/memory/state/current_state.json`
- `generate_plan`：切换到 planning 并触发 planner
- `modify_plan`：基于最新需求重新规划
- `continue_chat`：回到 chat，继续澄清
- `regenerate_plan`：从历史状态恢复后重生计划
- `go_interface`：进入 interface 节点补接口

> 注意：`last_user_action` 使用“边沿触发”。
> 同一个值连续重复传，后端会忽略重复动作，防止重复执行。

---

## 7. 持久化说明

每次 `/chat` 请求结束后，后端都会保存当前状态到：

`src/memory/state/current_state.json`

保存内容包括：
- `messages`
- `mode`
- `plan`
- `current_step`
- `mailbox`
- `ready_for_plan`
- `suggested_actions`
等核心字段。

---

## 8. 前端推荐调用范式

### 8.1 普通聊天
```json
{
  "session_id": "demo-001",
  "message": "我想做一个面向中小团队的任务管理系统"
}
```

### 8.2 保存前端编辑后的计划
```json
{
  "session_id": "demo-001",
  "plan": [
    {
      "id": 1,
      "description": "需求拆解",
      "status": "pending",
      "implementation_file": "src/planning/requirements.py",
      "interface": {
        "name": "collect_requirements",
        "parameters": [{"name": "raw_input", "type": "str"}],
        "return_type": "dict",
        "description": "整理需求",
        "dependencies": []
      }
    }
  ],
  "last_user_action": "save_plan"
}
```

### 8.3 让 AI 重新规划
```json
{
  "session_id": "demo-001",
  "message": "请把第一阶段改成先做登录和权限",
  "last_user_action": "modify_plan"
}
```

### `GET /state`
返回当前会话（或最近一次保存）的整体状态，供前端在页面加载时恢复 plan/requirements。

**Query**
- `session_id`（可选）：若提供且该 session 仍在内存中，则返回其最新状态；否则回退到 `src/memory/state/current_state.json` 或最近一次版本化文件。

**Response** 同 `POST /chat`，并同样包含重试可视化字段：`last_error_message`、`retry_count`、`retrying_node`、`progress_text`。

---

## 9. 注意事项

1. 建议前端始终复用同一 `session_id`，否则会创建新会话。
2. 手工改 plan 时，建议回传“完整 plan”，避免局部覆盖导致字段丢失。
3. 若前端要立即进入某动作，请优先通过 `last_user_action` 驱动。
