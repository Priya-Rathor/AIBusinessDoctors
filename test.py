from langchain.memory import ConversationSummaryBufferMemory
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

memory = ConversationSummaryBufferMemory(
    llm=llm,
    max_token_limit=1000,
    return_messages=True,
    memory_key="chat_history"
)

# Add messages manually
memory.chat_memory.add_user_message("Hello!")
memory.chat_memory.add_ai_message("Hi! How can I assist you?")
memory.chat_memory.add_user_message("Tell me how to start a clothing brand.")

# Print all stored messages
print("Messages:\n", memory.chat_memory.messages)

# Correct forced summary generation
summary = memory.predict_new_summary(memory.chat_memory.messages, memory.moving_summary_buffer)
memory.moving_summary_buffer = summary  # Optional: update internal state
print("\n✅ Forced Summary:\n", summary)
