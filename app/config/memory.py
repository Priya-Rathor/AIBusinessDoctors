from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from app.tools.search import search_tool
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

memory = MemorySaver()
llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools=[search_tool])
