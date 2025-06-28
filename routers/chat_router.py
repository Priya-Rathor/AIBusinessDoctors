from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from services.langgraph_engine import generate_chat_responses


chat_router = APIRouter()

@chat_router.get("/chat_stream")
async def chat_stream(message: str = Query(...), checkpoint_id: str = Query(None), clerk_id: str = Query(...), project_id: str = Query(...), chat_type: str = Query(...)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id, clerk_id, project_id, chat_type),
        media_type="text/event-stream"
    )