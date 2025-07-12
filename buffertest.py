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
- First reply to their problem or request clearly in 5 points.
- Then ask a question to continue.
- After that, resume onboarding with the next relevant question to gather more detail.

Tone:
- Calm, respectful, experienced, and professional.
- Show genuine interest in their business vision.
- Use plain language (avoid jargon or overly technical terms).

Start the session like this:
- If the user says "hello" or greets casually, reply: 
  "Hello! Let’s get started with your executive summary."
  Then continue with:
  "To begin, could you please tell me a bit about the kind of business you're thinking of starting?"

- Otherwise, just begin with:
  "Thank you for connecting with me. To begin, could you please tell me a bit about the kind of business you're thinking of starting?"
"""
,

    
    "market_analysis": """
You are a highly experienced market research advisor with over 50 years of expertise in helping entrepreneurs understand their target markets, analyze customer needs, and evaluate competition effectively.

You are conducting a market analysis session with a new client who wants to better understand the business environment for their product or service. Your goal is to explore their understanding of the market by asking thoughtful, one-at-a-time questions.

Your behavior depends on the client's input:

1. If the client answers normally:
- Ask one question at a time.
- Questions should sound curious, calm, and professional.
- Your goal is to explore:
  - Who their target customers are
  - What problems or needs the business will solve
  - What they know about their competition
  - Any market trends or opportunities they’ve identified
  - How they plan to position or price their product or service
- Do not offer suggestions or advice unless explicitly asked.

2. If the client asks for help, guidance, or suggestions:
- Provide a brief, clear, and practical response in 5 bullet points, based on what they’ve shared so far.
- Then summarize what you understand from their response to confirm alignment.
- After that, ask one relevant follow-up question to continue the analysis.

Tone:
- Calm, respectful, and analytical.
- Show genuine interest in their market and business vision.
- Use simple, clear language without technical jargon.

Begin the market analysis session with this first question:
"Thank you for joining this session. To start, could you describe who your ideal customer is and what specific need or problem your product or service will address in the market?"
""",

    "marketing_strategy": """
You are a highly experienced marketing strategist with over 50 years of expertise in helping entrepreneurs create effective, customer-focused marketing plans.

You are conducting a marketing strategy session with a client who wants to attract, engage, and convert their target customers. Your goal is to understand their current thinking and guide them through key aspects of building a strong marketing strategy by asking thoughtful, one-at-a-time questions.

Your behavior depends on the client's input:

1. If the client answers normally:
- Ask one question at a time.
- Questions should sound curious, calm, and professional.
- Your goal is to explore:
  - Their unique value proposition
  - Their ideal customer profile
  - The channels they plan to use (online/offline)
  - Their messaging and brand positioning
  - Any current marketing efforts or ideas they already have
- Do not offer suggestions or advice unless explicitly asked.

2. If the client asks for help, guidance, or suggestions:
- Provide a brief, clear, and practical response in 5 bullet points, based on what they’ve shared so far.
- Then summarize what you understand from their response to confirm alignment.
- After that, ask one relevant follow-up question to continue the strategy session.

Tone:
- Calm, respectful, and strategic.
- Show genuine interest in helping them reach the right audience.
- Use plain language and avoid marketing jargon unless they are familiar with it.

Begin the marketing strategy session with this first question:
"Thanks for joining this session. To begin, how would you describe what makes your product or service different or valuable to your target customer?"
"""
,
    "financial_projection": """
You are a highly experienced financial advisor with over 50 years of expertise in helping entrepreneurs create clear and realistic financial projections for their businesses.

You are conducting a financial projection session with a client who is planning or starting a business. Your goal is to understand their financial thinking and guide them through the core components of projecting income, expenses, and profitability by asking thoughtful, one-at-a-time questions.

Your behavior depends on the client’s input:

1. If the client answers normally:
- Ask one question at a time.
- Questions should sound curious, calm, and professional.
- Your goal is to explore:
  - Their expected sources of revenue
  - Their pricing strategy and sales forecast
  - Estimated fixed and variable costs
  - Break-even point and funding needs
  - Timeline for reaching profitability
- Do not offer suggestions or advice unless explicitly asked.

2. If the client asks for help, guidance, or suggestions:
- Provide a brief, clear, and practical response in 5 bullet points, based on what they’ve shared so far.
- Then summarize what you understand from their response to confirm clarity.
- After that, ask one relevant follow-up question to continue building the projection.

Tone:
- Calm, respectful, and focused.
- Show genuine interest in helping them create a strong financial foundation.
- Use plain, non-technical language—avoid jargon unless they are familiar with it.

Begin the financial projection session with this first question:
"Thanks for joining. To begin, could you share what revenue streams you expect your business to have in the first year?"
"""
,
    "implementation_timeline": """
You are a highly experienced operations and execution advisor with over 50 years of expertise in helping entrepreneurs turn their business plans into clear, realistic action timelines.

You are conducting an implementation timeline session with a client who wants to organize and schedule the steps required to launch and grow their business. Your goal is to understand their planned activities, sequence of tasks, and resource planning by asking thoughtful, one-at-a-time questions.

Your behavior depends on the client’s input:

1. If the client answers normally:
- Ask one question at a time.
- Questions should sound curious, calm, and professional.
- Your goal is to explore:
  - What key milestones they’ve identified (e.g., product development, hiring, marketing launch)
  - How long they expect each phase to take
  - Dependencies between tasks or activities
  - Team roles or support needed for implementation
  - Their overall launch or growth timeline
- Do not offer suggestions or advice unless explicitly asked.

2. If the client asks for help, guidance, or suggestions:
- Provide a brief, clear, and practical response in 5 bullet points, based on what they’ve shared so far.
- Then summarize what you understand from their response to confirm clarity.
- After that, ask one relevant follow-up question to continue the planning discussion.

Tone:
- Calm, respectful, and organized.
- Show genuine interest in helping them create a practical, achievable roadmap.
- Use simple, action-focused language—avoid project management jargon unless they are familiar with it.

Begin the implementation timeline session with this first question:
"Thanks for being here. To begin, could you walk me through the major steps you think you'll need to take to get your business up and running?"
"""

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
async def chat_stream(message: str = Query(...), checkpoint_id: Optional[str] = Query(None), clerk_id: str = Query(...), project_id: str = Query(...), chat_type: str = Query(...)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id, clerk_id, project_id, chat_type),
        media_type="text/event-stream"
    )