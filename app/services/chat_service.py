from typing import Optional
from uuid import uuid4
import json
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk
from app.prompts.onboarding import onboarding_prompt
from app.services.graph_builder import graph


def serialise_ai_message_chunk(chunk):
    if isinstance(chunk, AIMessageChunk):
        return chunk.content
    else:
        raise TypeError(f"Object of type {type(chunk).__name__} is not serialisable")


async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    is_new_conversation = checkpoint_id is None

    if is_new_conversation:
        new_checkpoint_id = str(uuid4())
        config = {"configurable": {"thread_id": new_checkpoint_id}}

        events = graph.astream_events(
            {"messages": [SystemMessage(content=onboarding_prompt), HumanMessage(content=message)]},
            version="v2",
            config=config
        )
        yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_checkpoint_id}\"}}\n\n"
    else:
        config = {"configurable": {"thread_id": checkpoint_id}}
        events = graph.astream_events(
            {"messages": [SystemMessage(content=onboarding_prompt), HumanMessage(content=message)]},
            version="v2",
            config=config
        )

    async for event in events:
        event_type = event["event"]

        if event_type == "on_chat_model_stream":
            content = serialise_ai_message_chunk(event["data"]["chunk"])
            safe = content.replace("'", "\\'").replace("\n", "\\n")
            yield f"data: {{\"type\": \"content\", \"content\": \"{safe}\"}}\n\n"

        elif event_type == "on_chat_model_end":
            tool_calls = getattr(event["data"]["output"], "tool_calls", [])
            for call in tool_calls:
                if call["name"] == "tavily_search_results_json":
                    query = call["args"].get("query", "")
                    yield f"data: {{\"type\": \"search_start\", \"query\": \"{query}\"}}\n\n"

        elif event_type == "on_tool_end" and event["name"] == "tavily_search_results_json":
            results = event["data"]["output"]
            urls = [item["url"] for item in results if isinstance(item, dict) and "url" in item]
            yield f"data: {{\"type\": \"search_results\", \"urls\": {json.dumps(urls)} }}\n\n"

    yield "data: {\"type\": \"end\"}\n\n"