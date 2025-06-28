from langchain_core.prompts import ChatPromptTemplate

summary_prompt = ChatPromptTemplate.from_template(
    "You are summarizing a chat with a client. Extract only one most important insight in the fewest words possible.\n\nCurrent summary:\n{summary}\nNew lines:\n{new_lines}"
)