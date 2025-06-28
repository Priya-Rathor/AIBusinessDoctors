from langchain.memory import ConversationSummaryBufferMemory
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

summary_prompt = ChatPromptTemplate.from_template(
    "You are summarizing a chat with a client. Extract only one most important insight in the fewest words possible.\n\nCurrent summary:\n{summary}\nNew lines:\n{new_lines}"
)

def create_memory(llm:ChatOpenAI):
    return ConversationSummaryBufferMemory(
        llm=llm,
        max_token_limit=1000,
        return_messages=True,
        memory_key="chat_history",
        prompt=summary_prompt
    )