from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage
from uuid import uuid4
from models.state import State
from tools.tavily_tool import search_tool, tools
from utils.serializers import serialise_ai_message_chunk
from utils.api_client import fetch_summary, save_summary
from prompts import get_prompt
from services.memory_manager import create_memory
from langgraph.graph import StateGraph, END
import json

llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools=tools)

async def model_node(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [result]}

async def tools_router(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END

async def tool_node(state: State):
    tool_calls = state["messages"][-1].tool_calls
    responses = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        if tool_name == "tavily_search_results_json":
            result = await search_tool.ainvoke(tool_args)
            responses.append({
                "content": str(result),
                "tool_call_id": tool_id,
                "name": tool_name
            })
    return {"messages": responses}

graph_builder = StateGraph(State)
graph_builder.add_node("model", model_node)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph = graph_builder.compile()

memory_store = {}

async def generate_chat_responses(message: str, checkpoint_id: str, clerk_id: str, project_id: str, chat_type: str):
    is_new = checkpoint_id is None
    prompt = get_prompt(chat_type)
    summary_text = fetch_summary(clerk_id, project_id, chat_type) if not is_new else ""

    initial_messages = [HumanMessage(role="system", content=prompt)]
    if summary_text:
        initial_messages.append(HumanMessage(role="system", content=f"Previous summary: {summary_text}"))
    initial_messages.append(HumanMessage(content=message))

    if is_new:
        checkpoint_id = str(uuid4())
        yield f"data: {json.dumps({'type': 'checkpoint', 'checkpoint_id': checkpoint_id})}\n\n"

    config = {"configurable": {"thread_id": checkpoint_id}}

    if checkpoint_id not in memory_store:
        memory_store[checkpoint_id] = create_memory(llm)

    memory = memory_store[checkpoint_id]

    events = graph.astream_events({"messages": initial_messages}, version="v2", config=config)

    ai_response = ""

    async for event in events:
        event_type = event["event"]

        if event_type == "on_chat_model_stream":
            chunk = serialise_ai_message_chunk(event["data"]["chunk"])
            ai_response += chunk
            yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"

        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            urls = [item["url"] for item in event["data"]["output"] if "url" in item]
            yield f"data: {json.dumps({'type': 'search_results', 'urls': urls})}\n\n"

    memory.chat_memory.add_user_message(message)
    memory.chat_memory.add_ai_message(ai_response)

    try:
        summary = memory.predict_new_summary(memory.chat_memory.messages, memory.moving_summary_buffer)
        memory.moving_summary_buffer = summary
        save_summary(clerk_id, project_id, chat_type, summary)
    except:
        pass

    yield f"data: {json.dumps({'type': 'end'})}\n\n"