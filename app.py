from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage , SystemMessage,AIMessage
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from uuid import uuid4
from langgraph.checkpoint.memory import MemorySaver
import httpx

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


system_prompt = (
    "You are a highly experienced business advisor with over 50 years of expertise in helping people start and grow successful businesses.\n\n"
    "You are conducting an onboarding session with a new client who wants to start a business. Your goal is to deeply understand their business idea by asking thoughtful, one-at-a-time questions.\n\n"
    "Your behavior depends on the client's input:\n\n"
    "1. If the client answers normally:\n"
    "- Ask one question at a time.\n"
    "- Questions should sound curious, calm, and professional.\n"
    "- Your goal is to explore what type of business they want to start, their motivation, target customers, goals, and available resources.\n"
    "- Do not give suggestions or advice unless explicitly asked.\n\n"
    "2. If the client asks for help, guidance, or suggestions:\n"
    "- Provide a brief, clear, and practical suggestion based on what they’ve shared so far.\n"
    "- Then revise what you understand from their response to confirm clarity.\n"
    "- First repley there problem or suggestion clear in 5 points then ask one question.\n  "
    "- After that, continue with the next relevant onboarding question to learn more.\n\n"
    "Tone:\n"
    "- Calm, respectful, experienced, and professional.\n"
    "- Show genuine interest in their business vision.\n"
    "- Use plain language (avoid jargon or overly technical terms).\n\n"
    "Begin the onboarding session with this first question:\n"
    "\"Thank you for connecting with me. To begin, could you please tell me a bit about the kind of business you're thinking of starting?\""
)

def serialise_ai_message_chunk(chunk): 
    if(isinstance(chunk, AIMessageChunk)):
        return chunk.content
    else:
        raise TypeError(
            f"Object of type {type(chunk).__name__} is not correctly formatted for serialisation"
        )









# -----------------------------------------------------------------------------------------------------------
#                                        Fetch last 10 messages
# ------------------------------------------------------------------------------------------------------------

async def fetch_last_messages(user_id:str,project_id:str,chat_type:str):
    url = f"http://192.168.1.64:5000/api/v1/chats/{user_id}/{project_id}/{chat_type}"


    async with httpx.AsyncClient() as client:
        response =  await client.get(url)
        response.raise_for_status()
        data = response.json()


        raw_messages = data.get("message_Data",{}).get("messages",[])
        last_messages = raw_messages[-9:]

        formatted_message = []
        for m in last_messages:
            role = m.get("role")
            content = m.get("content","")
            if role == "user":
                formatted_message.append(HumanMessage(content=content))
            elif role == "assistant":
                formatted_message.append(AIMessage(content=content))    
        return formatted_message

#-----------------------------------------------------------------------------------------------------------------------------------
#                                                Generate chat 
#------------------------------------------------------------------------------------------------------------------------------------




async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None,user_id:Optional[str]=None,project_id:Optional[str]=None,chat_type:Optional[str]=None):
    is_new_conversation = checkpoint_id is None

    previous_messages = []

    if user_id and project_id and chat_type:
        try:
            previous_messages = await fetch_last_messages(user_id,project_id,chat_type)
        except Exception as e:
            print("error fetching previous messages:", str(e))
    




    if is_new_conversation:
        # Generate new checkpoint ID for first message in conversation
        new_checkpoint_id = str(uuid4())

        config = {
            "configurable": {
                "thread_id": new_checkpoint_id
            }
        }
        
        # Initialize with first message
        events = graph.astream_events(
            {"messages":[
              SystemMessage(content=system_prompt),
              *previous_messages,
               HumanMessage(content=message)
            ]},
            version="v2",
            config=config
        )
        
        # First send the checkpoint ID
        yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
    else:
        config = {
            "configurable": {
                "thread_id": checkpoint_id
            }
        }
        # Continue existing conversation
        events = graph.astream_events(
            {"messages": [
                SystemMessage(content=system_prompt),
                *previous_messages,
                HumanMessage(content=message)
            ]},
            version="v2",
            config=config
        )

    async for event in events:
        event_type = event["event"]
        
        if event_type == "on_chat_model_stream":
            chunk_content = serialise_ai_message_chunk(event["data"]["chunk"])
            # Escape single quotes and newlines for safe JSON parsing
            safe_content = chunk_content.replace("'", "\\'").replace("\n", "\\n")
            
            yield f"data: {{\"type\": \"content\", \"content\": \"{safe_content}\"}}\n\n"
            
        elif event_type == "on_chat_model_end":
            # Check if there are tool calls for search
            tool_calls = event["data"]["output"].tool_calls if hasattr(event["data"]["output"], "tool_calls") else []
            search_calls = [call for call in tool_calls if call["name"] == "tavily_search_results_json"]
            
            if search_calls:
                # Signal that a search is starting
                search_query = search_calls[0]["args"].get("query", "")
                # Escape quotes and special characters
                safe_query = search_query.replace('"', '\\"').replace("'", "\\'").replace("\n", "\\n")
                yield f"data: {{\"type\": \"search_start\", \"query\": \"{safe_query}\"}}\n\n"
                
        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            # Search completed - send results or error
            output = event["data"]["output"]
            
            # Check if output is a list 
            if isinstance(output, list):
                # Extract URLs from list of search results
                urls = []
                for item in output:
                    if isinstance(item, dict) and "url" in item:
                        urls.append(item["url"])
                
                # Convert URLs to JSON and yield them
                urls_json = json.dumps(urls)
                yield f"data: {{\"type\": \"search_results\", \"urls\": {urls_json}}}\n\n"
    
    # Send an end event
    yield f"data: {{\"type\": \"end\"}}\n\n"

@app.get("/chat_stream")
async def chat_stream(message: str=Query(...), checkpoint_id: Optional[str] = Query(None), user_id:Optional[str]=Query(None), project_id:Optional[str]=Query(None),chat_type:Optional[str]=Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id), 
        media_type="text/event-stream"
    )

# SSE - server-sent events 



# install python version :- 3.11.9



# add prompt 
# add mongodb