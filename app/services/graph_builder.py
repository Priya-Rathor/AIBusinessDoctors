from langgraph.graph import add_messages, StateGraph, END
from app.models.state import State
from app.config.memory import memory, llm_with_tools
from app.tools.search import search_tool
from langchain_core.messages import ToolMessage


async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [result]}


async def tools_router(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END


async def tool_node(state: State):
    tool_calls = state["messages"][-1].tool_calls
    tool_messages = []

    for call in tool_calls:
        if call["name"] == "tavily_search_results_json":
            result = await search_tool.ainvoke(call["args"])
            tool_messages.append(ToolMessage(
                content=str(result),
                tool_call_id=call["id"],
                name=call["name"]
            ))

    return {"messages": tool_messages}


graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")

graph = graph_builder.compile(checkpointer=memory)
