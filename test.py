from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage , SystemMessage
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from uuid import uuid4
from langgraph.checkpoint.memory import MemorySaver

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
    

#---------------------------------------------------------------------------------------------------#                                   Prompt for different tools
# ----------------------------------------------------------------------------------------------


chat_type_prompts = {
    "executive_summary": (
        "You are a professional business consultant generating concise and compelling executive summaries "
        "for business plans. Focus on the main goals, value proposition, and vision."
    ),
    "market_analysis": (
        "You are a skilled market analyst. Provide a detailed market overview, trends, customer demographics, "
        "and competitor landscape."
    ),
    "marketing_strategy": (
        "You are an expert marketing strategist. Propose innovative and effective marketing plans including "
        "channels, messaging, and positioning."
    ),
    "financial_projection": (
        "You are a financial analyst. Project revenue, expenses, and profit margins clearly for a startup "
        "over 3–5 years."
    ),
    "implementation_timeline": (
        "You are an operations planner. Create a realistic implementation roadmap with clear milestones "
        "and timelines."
    ),
}



# ---------------------------------------------------------------------------------------
#                                  Global Memory Store
#---------------------------------------------------------------------------------------


async def generate_chat_responses(
    message: str,
    checkpoint_id: Optional[str],
    clerk_id: Optional[str],
    project_id: Optional[str],
    chat_type: str
):
    is_new_conversation = checkpoint_id is None

    system_prompt = chat_type_prompts.get(chat_type,"You are a helpful assistant.")
    print(f"[DEBUG] chat_type:{chat_type}")
    print(f"[DEBUG] system_prompt: {system_prompt}")

    initial_messages = [
        HumanMessage(role="system",content=system_prompt),
        HumanMessage(content=message)
    ]

    if is_new_conversation:
        new_checkpoint_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": new_checkpoint_id
            }
        }

        events = graph.astream_events(
            {"messages": initial_messages},
            version="v2",
            config=config
        )

        # ✅ Proper JSON-safe serialization
        yield f"data: {json.dumps({'type': 'checkpoint', 'checkpoint_id': new_checkpoint_id})}\n\n"
    else:
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }

        events = graph.astream_events(
            {"messages": initial_messages},
            version="v2",
            config=config
        )

    async for event in events:
        event_type = event["event"]

        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            # ✅ Use json.dumps to escape content safely
            yield f"data: {json.dumps({'type': 'content', 'content': chunk_content})}\n\n"

        elif event_type == "on_chat_model_end":
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]

            if search_calls:
                search_query = search_calls[0]["args"].get("query", "")
                # ✅ Use json.dumps to escape the query string properly
                yield f"data: {json.dumps({'type': 'search_start', 'query': search_query})}\n\n"

        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            output = event["data"]["output"]
            if isinstance(output, list):
                urls = [item["url"] for item in output if isinstance(item, dict) and "url" in item]
                # ✅ URLs already JSON-serializable
                yield f"data: {json.dumps({'type': 'search_results', 'urls': urls})}\n\n"

    # ✅ End of stream
    yield f"data: {json.dumps({'type': 'end'})}\n\n"






@app.get("/chat_stream")
async def chat_stream(message:str =Query(...),checkpoint_id:Optional[str]=Query(None) ,clerk_id: Optional[str]=Query(None), project_id: Optional[str]=Query(None),chat_type:str =Query(...)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id, clerk_id, project_id, chat_type),
        media_type="text/event-stream"
    )
# SSE - server-sent events 