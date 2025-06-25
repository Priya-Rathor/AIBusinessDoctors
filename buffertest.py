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

load_dotenv()






# Initialize memory saver for checkpointing
memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

search_tool = TavilySearchResults(
    max_results=4,
)

tools = [search_tool]

llm = ChatOpenAI(model="gpt-4o")

llm_with_tools = llm.bind_tools(tools=tools)






async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {
        "messages": [result], 
    }

async def tools_router(state: State):
    last_message = state["messages"][-1]

    if(hasattr(last_message, "tool_calls") and len(last_message.tool_calls) > 0):
        return "tool_node"
    else: 
        return END
    
async def tool_node(state):
    """Custom tool node that handles tool calls from the LLM."""
    # Get the tool calls from the last message
    tool_calls = state["messages"][-1].tool_calls
    
    # Initialize list to store tool messages
    tool_messages = []
    
    # Process each tool call
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]
        
        # Handle the search tool
        if tool_name == "tavily_search_results_json":
            # Execute the search tool with the provided arguments
            search_results = await search_tool.ainvoke(tool_args)
            
            # Create a ToolMessage for this result
            tool_message = ToolMessage(
                content=str(search_results),
                tool_call_id=tool_id,
                name=tool_name
            )
            
            tool_messages.append(tool_message)
    
    # Add the tool messages to the state
    return {"messages": tool_messages}

graph_builder = StateGraph(State)

graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")

graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")

graph = graph_builder.compile(checkpointer=memory)

app = FastAPI()

# Add CORS middleware with settings that match frontend requirements
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"], 
    expose_headers=["Content-Type"], 
)

def serialise_ai_message_chunk(chunk): 
    if(isinstance(chunk, AIMessageChunk)):
        return chunk.content
    else:
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )


memory_store ={}

async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    is_new_conversation = checkpoint_id is None

    # Step 1: Generate or reuse checkpoint ID
    if is_new_conversation:
        checkpoint_id = str(uuid4())
        yield f"data: {json.dumps({'type': 'checkpoint', 'checkpoint_id': checkpoint_id})}\n\n"

    config = {"configurable": {"thread_id": checkpoint_id}}

    # Step 2: Initialize memory if not already present
    if checkpoint_id not in memory_store:
        memory_store[checkpoint_id] = ConversationSummaryBufferMemory(
            llm=llm,  # Ensure llm = ChatOpenAI(...) is defined globally
            max_token_limit=1000,
            return_messages=True,
            memory_key="chat_history"
        )

    memory = memory_store[checkpoint_id]

    # Step 3: Create event stream from LangGraph
    events = graph.astream_events(
        {"messages": [HumanMessage(content=message)]},
        version="v2",
        config=config
    )

    ai_response = ""

    # Step 4: Stream LangGraph responses
    async for event in events:
        event_type = event["event"]

        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            ai_response += chunk_content
            yield f"data: {json.dumps({'type': 'content', 'content': chunk_content})}\n\n"

        elif event_type == "on_chat_model_end":
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]

            if search_calls:
                search_query = search_calls[0]["args"].get("query", "")
                yield f"data: {json.dumps({'type': 'search_start', 'query': search_query})}\n\n"

        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            output = event["data"]["output"]
            if isinstance(output, list):
                urls = [item["url"] for item in output if isinstance(item, dict) and "url" in item]
                yield f"data: {json.dumps({'type': 'search_results', 'urls': urls})}\n\n"

    # Step 5: Save user and AI messages in memory
    memory.chat_memory.add_user_message(message)
    memory.chat_memory.add_ai_message(ai_response)

    # Step 6: Generate summary manually (force trigger)
    summary = memory.predict_new_summary(memory.chat_memory.messages, memory.moving_summary_buffer)
    memory.moving_summary_buffer = summary

    print("🧠 Summary Generated:", summary)

    # Step 7: Format messages for backend structure
    formatted_messages = [
        {
            "id": idx + 1,
            "content": msg.content,
            "isUser": isinstance(msg, HumanMessage),
            "type": "message",
            "isLoading": False
        }
        for idx, msg in enumerate(memory.chat_memory.messages)
    ]

    # Step 8: Send POST request to your backend
    try:
        response = requests.post(
            "http://192.168.1.64:5000/api/v1/chats/chat-session/save",
            json={
                "clerk_id": "user_2yo9txIw82iYqozlxoyPvPWstWZ",
                "project_id": "685910ecd8dd65bc4e5498cf",
                "all_summarised_data": summary,
                "message_Data": {
                    "chat_type": "executive_summary",
                    "messages": formatted_messages,
                    "type_summarised_data": summary
                }
            }
        )

        print("✅ Summary POST response:", response.status_code, response.text)

    except Exception as e:
        print("❌ Error posting summary:", e)

    # Step 9: Signal end of SSE stream
    yield f"data: {json.dumps({'type': 'end'})}\n\n"











@app.get("/chat_stream")
async def chat_stream(message:str =Query(...),checkpoint_id:Optional[str]=Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id),
        media_type="text/event-stream"
    )
# SSE - server-sent events 