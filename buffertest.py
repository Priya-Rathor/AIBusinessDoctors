from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage, AIMessage
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from uuid import uuid4
from langgraph.checkpoint.memory import MemorySaver
from langchain.memory import ConversationSummaryBufferMemory
import requests
from langchain_core.prompts import ChatPromptTemplate

load_dotenv()

memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

search_tool = TavilySearchResults(max_results=4)
tools = [search_tool]
llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools=tools)

async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [result]}

async def tools_router(state: State):
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0:
        return "tool_node"
    else:
        return END

async def tool_node(state):
    tool_calls = state["messages"][-1].tool_calls
    tool_messages = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        if tool_name == "tavily_search_results_json":
            search_results = await search_tool.ainvoke(tool_args)
            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name
            )
            tool_messages.append(tool_message)
    return {"messages": tool_messages}

graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph = graph_builder.compile(checkpointer=memory)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Type"]
)

def serialise_ai_message_chunk(chunk):
    if isinstance(chunk, AIMessageChunk):
        return chunk.content
    else:
        raise TypeError(f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation")

chat_type_prompts = {
    "executive_summary": """
You are a highly experienced business advisor with over 50 years of expertise in helping people start and grow successful businesses.

You are conducting an onboarding session with a new client who wants to start a business. Your goal is to deeply understand their business idea by asking thoughtful, one-at-a-time questions.

Your behavior depends on the client's input:

1. If the client answers normally:
- Ask one question at a time.
- Questions should sound curious, calm, and professional.
- Your goal is to explore what type of business they want to start, their motivation, target customers, goals, and available resources.
- Do not give suggestions or advice unless explicitly asked.

2. If the client asks for help, guidance, or suggestions:
- Provide a brief, clear, and practical suggestion based on what they’ve shared so far.
- Then revise what you understand from their response to confirm clarity.
- First reply to their problem or suggestion clearly in 5 points, then ask one question.
- After that, continue with the next relevant onboarding question to learn more.

Tone:
- Calm, respectful, experienced, and professional.
- Show genuine interest in their business vision.
- Use plain language (avoid jargon or overly technical terms).


Begin the onboarding session with this first question:
"Thank you for connecting with me. To begin, could you please tell me a bit about the kind of business you're thinking of starting?"
""",

    
    "market_analysis": "You are a skilled market analyst. Provide a detailed market overview, trends, customer demographics, and competitor landscape.",
    "marketing_strategy": "You are an expert marketing strategist. Propose innovative and effective marketing plans including channels, messaging, and positioning.",
    "financial_projection": "You are a financial analyst. Project revenue, expenses, and profit margins clearly for a startup over 3–5 years.",
    "implementation_timeline": "You are an operations planner. Create a realistic implementation roadmap with clear milestones and timelines."
}

summary_prompt = ChatPromptTemplate.from_template(
    "You are summarizing a chat with a client. Extract only **one most important insight** in the **fewest words possible**.\n\nCurrent summary:\n{summary}\nNew lines:\n{new_lines}"
)

memory_store = {}

async def generate_chat_responses(message: str, checkpoint_id: Optional[str], clerk_id: Optional[str], project_id: Optional[str], chat_type: str):
    print("🔵 Incoming user message:", message)
    is_new_conversation = checkpoint_id is None
    system_prompt = chat_type_prompts.get(chat_type, "You are a helpful assistant.")
    summary_text = ""

    if checkpoint_id:
        summary_url = f"http://192.168.1.64:5000/api/v1/chats/{clerk_id}/{project_id}/{chat_type}"
        try:
            res = requests.get(summary_url)
            if res.status_code == 200:
                summary_data = res.json()
                summary_text = summary_data.get("content", "")
                print("📥 Retrieved summary for reload:", summary_text)
            else:
                print("⚠️ No summary found. Status:", res.status_code)
        except Exception as e:
            print("❌ Error fetching summary:", e)

    initial_messages = [HumanMessage(role="system", content=system_prompt)]
    if summary_text:
        initial_messages.append(HumanMessage(role="system", content=f"Previous conversation summary: {summary_text}"))
    initial_messages.append(HumanMessage(content=message))

    if is_new_conversation:
        checkpoint_id = str(uuid4())
        print("🆕 New conversation. Assigned checkpoint_id:", checkpoint_id)
        yield f"data: {json.dumps({'type': 'checkpoint', 'checkpoint_id': checkpoint_id})}\n\n"
    else:
        print("🟢 Resuming conversation with checkpoint_id:", checkpoint_id)

    config = {"configurable": {"thread_id": checkpoint_id}}

    if checkpoint_id not in memory_store:
        print("📦 Creating new memory for checkpoint:", checkpoint_id)
        memory_store[checkpoint_id] = ConversationSummaryBufferMemory(
            llm=llm,
            max_token_limit=1000,
            return_messages=True,
            memory_key="chat_history",
            prompt=summary_prompt
        )
    else:
        print("📥 Loaded existing memory for checkpoint:", checkpoint_id)

    memory = memory_store[checkpoint_id]

    print("⚙️ Starting LangGraph stream...")
    events = graph.astream_events({"messages": initial_messages}, version="v2", config=config)

    ai_response = ""
    streamed = False

    async for event in events:
        event_type = event["event"]
        print("📡 Received event:", event_type)

        if event_type == "on_chat_model_stream":
            streamed = True
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            ai_response += chunk_content
            yield f"data: {json.dumps({'type': 'content', 'content': chunk_content})}\n\n"

        elif event_type == "on_chat_model_end":
            print("✅ Finished AI generation")
            tool_calls = getattr(event["data"]["output"], "tool_calls", [])
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            if search_calls:
                search_query = search_calls[0]["args"].get("query", "")
                print("🔍 Search tool used for query:", search_query)
                yield f"data: {json.dumps({'type': 'search_start', 'query': search_query})}\n\n"

        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            output = event["data"]["output"]
            if isinstance(output, list):
                urls = [item["url"] for item in output if isinstance(item, dict) and "url" in item]
                print("🔗 Search results URLs:", urls)
                yield f"data: {json.dumps({'type': 'search_results', 'urls': urls})}\n\n"

    print("🧠 Updating memory with user + AI messages")
    memory.chat_memory.add_user_message(message)
    memory.chat_memory.add_ai_message(ai_response)
    print("🧠 Total messages in memory:", len(memory.chat_memory.messages))

    try:
        summary = memory.predict_new_summary(memory.chat_memory.messages, memory.moving_summary_buffer)
        memory.moving_summary_buffer = summary
        print("📘 Summary generated:\n", summary)
    except Exception as e:
        summary = ""
        print("❌ Error generating summary:", e)

    payload = {"content": summary}
    put_url = f"http://192.168.1.64:5000/api/v1/chats/save-type-summary/{clerk_id}/{project_id}/{chat_type}"

    print("📤 Sending PUT request to MongoDB API...")
    try:
        response = requests.put(put_url, json=payload)
        print("✅ PUT response:", response.status_code, response.text)
    except Exception as e:
        print("❌ Failed to PUT to MongoDB API:", e)

    yield f"data: {json.dumps({'type': 'end'})}\n\n"

@app.get("/chat_stream")
async def chat_stream(message: str = Query(...), checkpoint_id: Optional[str] = Query(None), clerk_id: Optional[str] = Query(None), project_id: Optional[str] = Query(None), chat_type: str = Query(...)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id, clerk_id, project_id, chat_type),
        media_type="text/event-stream"
    )