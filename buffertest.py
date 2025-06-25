from langchain.memory import ConversationBufferMemory
from langchain.chains import ConversationChain
from langchain_openai import ChatOpenAI
import asyncio

llm = ChatOpenAI(model="gpt-4o")

summary_memory = ConversationBufferMemory(
    llm = llm,
    return_messages=True
)

conversation = ConversationChain(
    llm = llm,
    memory  = summary_memory
)


async def run_conversation():
    print("\n -----Chat Starts ---\n")

    await conversation.arun("Hi, I want to open a food delivery business.")
    await conversation.arun("I want to target office workers and student.")
    await conversation.arun("I have a team of 3 and a small budget.")
    await conversation.arun("Can you suggest how I should begin?")


    # show current memory buffer(summary)

    print("\ Summary ")

    print(summary_memory.buffer)


    await conversation.arun("What should be my launch strategy?")
    await conversation.arun("How can I test the market first?")


    # show updated summary

    print("\n ---Final summary ---\n")
    print(summary_memory.buffer)

    