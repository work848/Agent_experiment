from agent.state import AgentState, Mode, NextNode, RunStatus, ApprovalType


RETRY_PROGRESS = {
    NextNode.PLANNER: "当前进度：需求已整理，正在重新生成开发计划。",
    NextNode.INTERFACE: "当前进度：开发计划已生成，正在重新补全接口定义。",
}

FINAL_PROGRESS = {
    NextNode.PLANNER: "当前进度停留在开发计划生成阶段，请调整需求描述后再试。",
    NextNode.INTERFACE: "当前进度停留在接口定义补全阶段。",
}


def _node_label(node: NextNode | None) -> str:
    if node == NextNode.PLANNER:
        return "规划节点（planner）"
    if node == NextNode.INTERFACE:
        return "接口节点（interface）"
    return "错误节点"


def error_node(state: AgentState):
    failed_node = state.last_failed_node
    if failed_node is None:
        return {
            "next_node": NextNode.END,
            "retrying_node": None,
            "run_status": RunStatus.IDLE,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }

    node_label = _node_label(failed_node)

    if state.retry_count < state.max_node_retries:
        retry_count = state.retry_count + 1
        progress_text = RETRY_PROGRESS.get(failed_node, "当前任务正在自动重试。")
        retry_message = {
            "role": "assistant",
            "content": f"{node_label}生成失败，正在自动重试 {retry_count}/{state.max_node_retries}。{progress_text}",
        }

        updates = {
            "current_agent": NextNode.ERROR,
            "mode": Mode.PLANNING,
            "retry_count": retry_count,
            "retrying_node": failed_node.value,
            "progress_text": progress_text,
            "messages": state.messages + [retry_message],
            "last_error_message": state.last_error_message,
            "last_failed_node": failed_node,
            "run_status": RunStatus.RUNNING,
            "approval_required": False,
            "approval_type": None,
            "approval_payload": None,
        }

        if failed_node == NextNode.PLANNER:
            updates.update(
                {
                    "trigger_plan": True,
                    "interface_refresh": False,
                    "next_node": NextNode.PLANNER,
                }
            )
            return updates

        if failed_node == NextNode.INTERFACE:
            updates.update(
                {
                    "trigger_plan": False,
                    "interface_refresh": True,
                    "next_node": NextNode.INTERFACE,
                }
            )
            return updates

    progress_text = FINAL_PROGRESS.get(failed_node, "当前任务执行失败。")
    final_error = state.last_error_message or f"{node_label}执行失败。"
    final_message = {
        "role": "assistant",
        "content": f"{final_error}已自动重试一次，但仍未成功。{progress_text}",
    }
    return {
        "current_agent": NextNode.ERROR,
        "mode": Mode.PLANNING,
        "trigger_plan": False,
        "interface_refresh": False,
        "next_node": NextNode.END,
        "messages": state.messages + [final_message],
        "retrying_node": None,
        "progress_text": progress_text,
        "run_status": RunStatus.WAITING_APPROVAL,
        "approval_required": True,
        "approval_type": ApprovalType.RETRY_AFTER_FAILURE,
        "approval_payload": {
            "failed_node": failed_node.value,
            "error_message": final_error,
            "retry_count": state.retry_count,
            "max_retries": state.max_node_retries,
        },
    }
