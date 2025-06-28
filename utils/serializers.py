from langchain_core.messages import AIMessageChunk

def serialise_ai_message_chunk(chunk):
    if isinstance(chunk, AIMessageChunk):
        return chunk.content
    else:
        raise TypeError(f"Invalid chunk Type: {type(chunk).__name__}")