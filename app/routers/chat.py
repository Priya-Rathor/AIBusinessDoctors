from fastapi import APIRouter ,Query
from fastapi.responses import StreamingResponse
from typing import Optional
from app.services.chat_service import generate_chat_responses

router  = APIRouter()

@router.get("/chat_stream")
async def chat_stream(message:str =Query(...),checkpoint_id:Optional[str]=Query(None)):
    return StreamingResponse(
        generate_chat_responses(message, checkpoint_id),
        media_type="text/event-stream"
    )
