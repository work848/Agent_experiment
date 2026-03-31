# API Chat 前端联调手册（Playbook）

> 面向前端开发联调，重点关注：按钮行为、请求 payload、页面状态更新。

基础 API 说明见：`API_CHAT_DOC.md`

---

## 1. 一图看流程（前端视角）

```text
用户输入 message
   ↓ POST /chat
后端 chat 回复
   ├─ 若 ready_for_plan=false：继续聊天澄清
   └─ 若 ready_for_plan=true：本次提示“下一次自动生成计划”

下一次任意 /chat 请求
   ↓
后端自动进入 planning -> planner 产出 step -> interface 补全接口
   ↓
返回 plan（含 interface）给前端 + 保存 current_state.json

用户在前端编辑 plan/interface
   ↓ 点击 Save Plan
POST /chat (plan + last_user_action=save_plan)
   ↓
保存到 current_state.json

用户提出修改意见
   ↓ POST /chat (message + last_user_action=modify_plan)
重新规划并更新 plan/interface
```

---

## 2. 前端状态建议

建议页面维护以下本地状态：

```ts
type UiState = {
  sessionId: string
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
  plan: Step[]
  readyForPlan: boolean
  actions: Array<{ action: string; label: string }>
  currentStep: number
  agents: { planner: string; coder: string; tester: string }
  logs: string[]
  lastErrorMessage: string | null
  retryCount: number
  retryingNode: 'planner' | 'interface' | null
  progressText: string | null
}
```

以接口返回为准更新，避免前端自行推导业务状态。

---

## 3. 按钮 → API payload 映射

## 3.1 发送聊天（发送按钮）

**用途**：普通对话、补充需求、触发“下一次自动规划”

```json
{
  "session_id": "demo-001",
  "message": "我希望支持多人协作和任务看板"
}
```

前端处理：
- 用返回的 `messages` 覆盖聊天区
- 用返回的 `ready_for_plan` 和 `actions` 刷新 CTA 区
- 若返回 `plan` 非空，刷新计划面板

---

## 3.2 保存用户编辑后的计划（Save Plan 按钮）

**用途**：把前端改过的 step/interface 持久化

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
        "parameters": [{ "name": "raw_input", "type": "str" }],
        "return_type": "dict",
        "description": "整理需求",
        "dependencies": []
      }
    }
  ],
  "last_user_action": "save_plan"
}
```

前端处理：
- 以返回的 `plan` 为最终真值（服务端可能做了归一化）
- 给用户提示“已保存”

---

## 3.3 让 AI 改进计划（Regenerate/Improve 按钮）

**用途**：用户指出问题，AI 重新规划

```json
{
  "session_id": "demo-001",
  "message": "第一阶段先做登录和权限控制，再做任务流转",
  "last_user_action": "modify_plan"
}
```

可选：若你希望带上当前手工编辑版本供后端先接管，也可同时传 `plan`。

前端处理：
- 显示“AI 正在更新计划”
- 响应回来后整体替换 `plan`

---

## 3.4 继续补充（Continue Chat 按钮）

```json
{
  "session_id": "demo-001",
  "last_user_action": "continue_chat"
}
```

通常可直接让用户继续输入 message；该动作用于显式切回 chat 模式。

---

## 3.5 手动立即生成计划（Generate Plan 按钮，兜底）

```json
{
  "session_id": "demo-001",
  "last_user_action": "generate_plan"
}
```

用于用户不想继续聊、希望立刻进入规划。

---

## 4. 渲染规则（最重要）

### 4.1 Chat 面板
- 永远展示 `messages`
- 以最后一条 assistant 文本作为最新回复

### 4.2 CTA 区（建议操作按钮）
- 当 `actions.length > 0` 时展示按钮
- 按钮直接映射到 `last_user_action`

### 4.3 Plan 面板
- 当 `plan.length > 0` 时展示步骤列表
- 每个 step 展示：`id/description/status/implementation_file/interface`
- `status` 使用接口返回值（已归一化到 pending/running/failed/done）

### 4.4 Agent 状态条
- 使用 `agents` 渲染“planner/coder/tester 是否 working”

### 4.5 重试态 / 进度态
- 当 `retrying_node` 不为 `null` 时：展示“系统正在自动重试 {retrying_node}”
- 同时展示 `progress_text`，不要自己拼文案
- `messages` 最后一条 assistant 通常也会带“正在自动重试 1/1”提示，可直接显示在聊天流里
- 当 `last_error_message` 非空且 `retrying_node=null` 且最后一条 assistant 为失败提示时，可展示失败态 banner

推荐映射：
- `retrying_node='planner'`：显示“正在重新生成开发计划”
- `retrying_node='interface'`：显示“正在重新补全接口定义”

---

## 5. 推荐时序（避免误判）

### 阶段 1：信息不足
- 用户发消息 -> 返回 chat 回复，`ready_for_plan=false`

### 阶段 2：刚达到阈值
- 这次返回提示文案（不是 plan）
- `ready_for_plan=true`，`actions` 出现

### 阶段 3：下一次请求
- 自动进入 planning + interface
- 返回非空 `plan`

> 注意：这是“先提示，再自动规划”的两段式体验。

---

## 6. 常见坑与规避

## 6.1 重复 action 不生效
原因：后端对 `last_user_action` 做了边沿触发去重。

规避：
- 同一个 action 连续触发前，可先发一次 `last_user_action=null` 的普通请求，或让用户先输入 message。
- 前端按钮点击后先禁用，待响应回来再恢复。

## 6.2 session_id 变化导致上下文丢失
规避：
- 页面加载时：
  - 优先从本地存储恢复 `session_id`
  - 若存在 `session_id`，立即调用 `GET /state?session_id=<id>`，若 HTTP 200 则用响应覆盖本地 `messages/plan/requirements/current_step/actions/ready_for_plan`
  - 若返回 404 或无 session，可自动进入空白状态并等待用户输入

## 6.3 仅传部分 plan 导致字段丢失
规避：
- Save Plan 时回传完整 `plan` 数组，不要只传局部 patch

## 6.4 本地 optimistic UI 与服务端不一致
规避：
- 所有操作后用响应里的 `messages/plan/actions` 覆盖本地状态

---

## 7. 前端最小调用封装（示例）

```ts
async function postChat(payload: any) {
  const res = await fetch('http://localhost:8000/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

function syncFromServer(data: any) {
  ui.messages = data.messages ?? []
  ui.plan = data.plan ?? []
  ui.readyForPlan = !!data.ready_for_plan
  ui.actions = data.actions ?? []
  ui.currentStep = data.current_step ?? 0
  ui.agents = data.agents ?? { planner: 'idle', coder: 'idle', tester: 'idle' }
  ui.logs = data.logs ?? []
  ui.lastErrorMessage = data.last_error_message ?? null
  ui.retryCount = data.retry_count ?? 0
  ui.retryingNode = data.retrying_node ?? null
  ui.progressText = data.progress_text ?? null
}
```

---

## 8. 联调 Checklist

- [ ] 同一 `session_id` 连续请求
- [ ] 达阈值后先看到提示文案
- [ ] 下一次请求返回非空 `plan`
- [ ] `plan.interface` 字段可见
- [ ] 编辑后 `save_plan` 能持久化
- [ ] `modify_plan` 能重生并更新 `plan`
- [ ] planner 首次失败时，返回 `retrying_node=planner`、`retry_count=1`
- [ ] interface 首次失败时，返回 `retrying_node=interface`、`retry_count=1`
- [ ] 自动重试成功后，`retrying_node=null`、`retry_count=0`
- [ ] 自动重试失败后，`last_error_message` 和最终失败文案可见
- [ ] 连续普通 chat 不触发递归错误

---

如需，我可以再补一版「React 组件状态流转图 + 按钮禁用/Loading 规则」给你直接贴到前端项目里。
