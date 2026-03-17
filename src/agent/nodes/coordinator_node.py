from langgraph.graph import StateGraph, END
from agent.state import AgentState



def central_coordinator(state: AgentState):
    # 工具调用流程
    if state.tool_call:
        return state.current_agent
    
    # 邮件调用流程
    for mail in state.mailbox:
        if not mail.is_resolved:
            return mail.target
    if state.success:
        return END
    
    
    #正常流程
    if state.current_agent == "planner":
        return "interface"

    if state.current_agent == "interface":
        return END

    # if state.current_agent == "coder":
    #     return "executor"

    # if state.current_agent == "executor":
    #     return "tester"

    # if state.current_agent == "tester":
    #     return END
    return END