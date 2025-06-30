

# install python version :- 3.11.9




Here is a detailed `README.md` file with clear explanations for each part of your chatbot project:

---


# 🧠 Business Advisor Chatbot (FastAPI + LangGraph)

This project is a **modular, scalable chatbot** built with **FastAPI**, **LangGraph**, and **LangChain**. It supports **multi-turn conversations**, **memory summarization**, and **tool integration** (Tavily search). Designed for helping entrepreneurs and business users through structured prompts like executive summaries, market analysis, marketing strategies, and more.

---

## 📁 Project Structure

```

my\_chatbot\_project/
│
├── main.py                  # App entry, loads FastAPI + routers
├── requirements.txt         # All dependencies
├── .env                     # API keys and secrets
│
├── config/                  # Global app settings
│   └── settings.py
│
├── routers/                 # API endpoint definitions
│   └── chat\_router.py
│
├── services/                # LangGraph logic, memory, summaries
│   ├── langgraph\_engine.py
│   ├── memory\_manager.py
│   └── summarizer.py
│
├── models/                  # Shared types
│   └── state.py
│
├── tools/                   # External tool setup (Tavily search)
│   └── tavily\_tool.py
│
├── prompts/                 # Dynamic prompt templates per chat\_type
│   ├── executive\_summary.py
│   ├── market\_analysis.py
│   ├── marketing\_strategy.py
│   ├── financial\_projection.py
│   ├── implementation\_timeline.py
│   ├── default\_prompt.py
│   └── **init**.py
│
├── utils/                   # Utilities
│   ├── serializers.py
│   └── api\_client.py
│
├── test/                    # Unit test directory
│   └── test\_chat\_stream.py
│
└── README.md                # Project documentation

````

---

## 🚀 Setup Instructions

### 1. Clone the repo

```bash
git clone https://github.com/yourname/my_chatbot_project.git
cd my_chatbot_project
````

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up your `.env` file

Create a `.env` file in the root with the following keys:

```
OPENAI_API_KEY=your-openai-key
TAVILY_API_KEY=your-tavily-key
```

---

## 🛠️ How It Works

### ✅ FastAPI Endpoint

`/chat_stream` is the main streaming endpoint using Server-Sent Events (SSE). It takes:

* `message` – the user's question
* `checkpoint_id` – resume previous context or None
* `clerk_id`, `project_id` – user/project context
* `chat_type` – type of session (e.g., "market\_analysis")

### 🧠 Memory & Summarization

* Uses `ConversationSummaryBufferMemory` to summarize long chats.
* Automatically updates memory every round.
* Sends/receives chat summaries via REST API (`utils/api_client.py`).

### 🧩 LangGraph Integration

* Manages flow: model node → conditional → tool node → back to model.
* Asynchronously streams responses via `langgraph.astream_events`.

### 🔍 Tools

* Integrated with **Tavily** for real-time web search.
* You can extend `tools/` for custom tools later.

### 💬 Prompt Templates

* Prompts are modularized in `prompts/` for each type:

  * `executive_summary`, `market_analysis`, etc.
* `prompts/__init__.py` dynamically loads the right one.

---

## 🔥 Example API Usage

### Curl Request

```bash
curl -N "http://localhost:8000/chat_stream?message=Hi&clerk_id=123&project_id=456&chat_type=executive_summary"
```

### Expected Response (SSE stream)

```json
data: {"type":"checkpoint", "checkpoint_id":"uuid"}
data: {"type":"content", "content":"Hello! Let’s get started..."}
data: {"type":"end"}
```

---


## 📘 Supported Chat Types

* `executive_summary`
* `market_analysis`
* `marketing_strategy`
* `financial_projection`
* `implementation_timeline`

These drive dynamic onboarding experiences using specialized prompts.

---

## 🧪 Testing

You can write tests using `pytest` in the `test/` directory.

Example test:

```bash
pytest test/test_chat_stream.py
```


---

## 🧩 Extending This Bot

* Add new prompts to `prompts/`
* Register them in `__init__.py`
* Add new tools in `tools/`
* Enhance summarization logic in `services/summarizer.py`

---


## 🙏 Credits

* [LangChain](https://github.com/langchain-ai/langchain)
* [LangGraph](https://github.com/langchain-ai/langgraph)
* [Tavily Search](https://www.tavily.com/)
* Built with ❤️ by \[Your Name]

---

```
