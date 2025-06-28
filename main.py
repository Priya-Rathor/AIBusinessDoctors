from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers.chat_router import chat_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers =["Content-Type"]
)


app.include_router(chat_router)