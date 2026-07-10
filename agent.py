# """
# ===============================================================================
#                 BIGQUERY + GOOGLE SEARCH + GEMINI CHATBOT APP
# ===============================================================================



#############################################################################################
#############################################################################################
## WITH GOOGLE WEB SEARCH
#############################################################################################
#############################################################################################

# Features:
# - Queries BigQuery table: gen-ai-ac.carbon1.tb-carbon
# - Falls back to Google Search when BigQuery has no answer
# - Falls back to Gemini model when Google Search also fails
# - Provides live progress states in the chat UI:
#   thinking, analyzing, searching, finalizing
# - Runs as a Flask web application

# Requirements:
# - Flask
# - requests
# - google-cloud-bigquery
# - google-genai

# Environment Variables:
# - FLASK_SECRET_KEY
# - GOOGLE_APPLICATION_CREDENTIALS
# - GOOGLE_SEARCH_API_KEY
# - GOOGLE_SEARCH_ENGINE_ID
# - GOOGLE_CLOUD_LOCATION
# ===============================================================================
# """

# import os
# import json
# import uuid
# import threading
# from datetime import date, datetime
# from decimal import Decimal
# from typing import Any, Dict, List

# import requests
# from flask import Flask, render_template, request, jsonify, session
# from google.cloud import bigquery
# from google import genai
# from google.genai import types


# # -----------------------------------------------------------------------------
# # Flask app setup
# # -----------------------------------------------------------------------------
# app = Flask(__name__)
# app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")


# # -----------------------------------------------------------------------------
# # Configuration
# # -----------------------------------------------------------------------------
# PROJECT_ID = "gen-ai-ac"
# DATASET_ID = "carbon1"
# TABLE_ID = "tb-carbon"
# FULL_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

# MODEL_NAME = "gemini-2.5-flash"
# LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

# GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
# GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID", "")


# # -----------------------------------------------------------------------------
# # Shared in-memory chat state
# # -----------------------------------------------------------------------------
# CHAT_STATE: Dict[str, Dict[str, Any]] = {}
# STATE_LOCK = threading.Lock()


# # -----------------------------------------------------------------------------
# # JSON-safe conversion helpers
# # -----------------------------------------------------------------------------
# def json_safe(obj: Any) -> Any:
#     """Convert dates, datetimes, decimals, and nested values into JSON-safe types."""
#     if isinstance(obj, (datetime, date)):
#         return obj.isoformat()
#     if isinstance(obj, Decimal):
#         return float(obj)
#     if isinstance(obj, dict):
#         return {str(k): json_safe(v) for k, v in obj.items()}
#     if isinstance(obj, list):
#         return [json_safe(v) for v in obj]
#     if isinstance(obj, tuple):
#         return [json_safe(v) for v in obj]
#     return obj


# def dumps_safe(obj: Any, **kwargs) -> str:
#     """JSON dump helper that always handles BigQuery-friendly values."""
#     return json.dumps(json_safe(obj), **kwargs)


# # -----------------------------------------------------------------------------
# # BigQuery sub-agent
# # -----------------------------------------------------------------------------
# class BigQuerySubAgent:
#     """Handles all BigQuery-related operations."""

#     def __init__(self, project_id: str, dataset_id: str, table_id: str):
#         self.full_table_id = f"{project_id}.{dataset_id}.{table_id}"
#         self.client = bigquery.Client(project=project_id)

#     def get_table_schema(self) -> Dict[str, Any]:
#         """Return table schema and metadata."""
#         table = self.client.get_table(self.full_table_id)
#         return json_safe({
#             "table": self.full_table_id,
#             "num_rows": table.num_rows,
#             "num_columns": len(table.schema),
#             "schema": [
#                 {
#                     "name": f.name,
#                     "type": f.field_type,
#                     "mode": f.mode,
#                     "description": f.description,
#                 }
#                 for f in table.schema
#             ],
#         })

#     def preview_rows(self, limit: int = 10) -> List[Dict[str, Any]]:
#         """Fetch a small sample of rows from the table."""
#         sql = f"SELECT * FROM `{self.full_table_id}` LIMIT {int(limit)}"
#         rows = self.client.query(sql).result()
#         return json_safe([dict(r.items()) for r in rows])

#     def run_sql(self, sql: str, max_rows: int = 100) -> List[Dict[str, Any]]:
#         """Run arbitrary SQL and return rows."""
#         rows = self.client.query(sql).result()
#         return json_safe([dict(r.items()) for _, r in zip(range(max_rows), rows)])

#     def ask_data_insights(self, question: str) -> Dict[str, Any]:
#         """Prepare structured BigQuery context for the model."""
#         schema = self.get_table_schema()
#         sample = self.preview_rows(limit=10)
#         return json_safe({
#             "source": "bigquery",
#             "table": self.full_table_id,
#             "question": question,
#             "schema": schema,
#             "sample_rows": sample,
#         })


# # -----------------------------------------------------------------------------
# # Google Search sub-agent
# # -----------------------------------------------------------------------------
# def google_search(query: str, max_results: int = 5) -> Dict[str, Any]:
#     """
#     Search Google using the Custom Search JSON API.
#     """
#     if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
#         return {
#             "source": "google_search",
#             "query": query,
#             "results": [],
#             "error": "Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID.",
#         }

#     url = "https://www.googleapis.com/customsearch/v1"
#     params = {
#         "key": GOOGLE_SEARCH_API_KEY,
#         "cx": GOOGLE_SEARCH_ENGINE_ID,
#         "q": query,
#         "num": min(max_results, 10),
#     }

#     try:
#         resp = requests.get(url, params=params, timeout=30)
#         resp.raise_for_status()
#         data = resp.json()

#         results = []
#         for item in data.get("items", [])[:max_results]:
#             results.append({
#                 "title": item.get("title"),
#                 "link": item.get("link"),
#                 "snippet": item.get("snippet"),
#                 "displayLink": item.get("displayLink"),
#             })

#         return json_safe({
#             "source": "google_search",
#             "query": query,
#             "results": results,
#         })
#     except Exception as e:
#         return json_safe({
#             "source": "google_search",
#             "query": query,
#             "results": [],
#             "error": str(e),
#         })


# # -----------------------------------------------------------------------------
# # Root agent initialization
# # -----------------------------------------------------------------------------
# bq_agent = BigQuerySubAgent(PROJECT_ID, DATASET_ID, TABLE_ID)
# client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)


# # -----------------------------------------------------------------------------
# # Tool declarations for Gemini function calling
# # -----------------------------------------------------------------------------
# tools = [
#     types.Tool(
#         function_declarations=[
#             types.FunctionDeclaration(
#                 name="get_table_schema",
#                 description="Get BigQuery table schema and metadata.",
#                 parameters={"type": "object", "properties": {}},
#             ),
#             types.FunctionDeclaration(
#                 name="preview_rows",
#                 description="Preview rows from the BigQuery table.",
#                 parameters={
#                     "type": "object",
#                     "properties": {"limit": {"type": "integer", "default": 10}},
#                 },
#             ),
#             types.FunctionDeclaration(
#                 name="run_sql",
#                 description="Run SQL against the BigQuery table.",
#                 parameters={
#                     "type": "object",
#                     "properties": {
#                         "sql": {"type": "string"},
#                         "max_rows": {"type": "integer", "default": 100},
#                     },
#                     "required": ["sql"],
#                 },
#             ),
#             types.FunctionDeclaration(
#                 name="ask_data_insights",
#                 description="Analyze the BigQuery table and return insight-oriented context.",
#                 parameters={
#                     "type": "object",
#                     "properties": {"question": {"type": "string"}},
#                     "required": ["question"],
#                 },
#             ),
#             types.FunctionDeclaration(
#                 name="google_search",
#                 description="Search Google when the answer is not found in BigQuery.",
#                 parameters={
#                     "type": "object",
#                     "properties": {
#                         "query": {"type": "string"},
#                         "max_results": {"type": "integer", "default": 5},
#                     },
#                     "required": ["query"],
#                 },
#             ),
#             types.FunctionDeclaration(
#                 name="model_fallback",
#                 description="Ask the Gemini model itself when both BigQuery and Google Search fail.",
#                 parameters={
#                     "type": "object",
#                     "properties": {"question": {"type": "string"}},
#                     "required": ["question"],
#                 },
#             ),
#         ]
#     )
# ]


# # -----------------------------------------------------------------------------
# # System prompt for root agent
# # -----------------------------------------------------------------------------
# SYSTEM_PROMPT = f"""
# You are the root agent for a data assistant.

# Available sources:
# 1. BigQuery table `{FULL_TABLE_ID}`
# 2. Google Search fallback
# 3. Gemini model fallback when Google Search has no useful result

# Decision policy:
# - Prefer BigQuery for table-related, numeric, historical, or internal questions.
# - If the answer is not present in the table, use google_search.
# - If google_search returns no useful results or the question is general knowledge, use model_fallback.
# - If the question is ambiguous, inspect schema or sample rows first.
# - If neither source can answer, say what is missing.

# Return short, direct answers.
# """


# # -----------------------------------------------------------------------------
# # Gemini model fallback
# # -----------------------------------------------------------------------------
# def model_fallback(question: str) -> str:
#     """Use Gemini directly when web search is not useful."""
#     resp = client.models.generate_content(
#         model=MODEL_NAME,
#         contents=[types.Content(role="user", parts=[types.Part(text=question)])],
#         config=types.GenerateContentConfig(temperature=0.2),
#     )
#     return resp.text or ""


# # -----------------------------------------------------------------------------
# # Tool execution router
# # -----------------------------------------------------------------------------
# def execute_tool_call(name: str, args: Dict[str, Any]) -> Any:
#     """Route Gemini function calls to the appropriate backend tool."""
#     if name == "get_table_schema":
#         return bq_agent.get_table_schema()
#     if name == "preview_rows":
#         return bq_agent.preview_rows(limit=args.get("limit", 10))
#     if name == "run_sql":
#         return bq_agent.run_sql(sql=args["sql"], max_rows=args.get("max_rows", 100))
#     if name == "ask_data_insights":
#         return bq_agent.ask_data_insights(question=args["question"])
#     if name == "google_search":
#         return google_search(query=args["query"], max_results=args.get("max_results", 5))
#     if name == "model_fallback":
#         return {"source": "model_fallback", "answer": model_fallback(args["question"])}
#     raise ValueError(f"Unknown tool: {name}")


# # -----------------------------------------------------------------------------
# # Main reasoning function
# # -----------------------------------------------------------------------------
# def analyze_question(user_question: str, progress_cb=None) -> str:
#     """Run the root agent and provide live progress updates."""
#     def update(stage: str, detail: str = ""):
#         if progress_cb:
#             progress_cb(stage, detail)

#     update("thinking", "Preparing answer")

#     contents = [types.Content(role="user", parts=[types.Part(text=user_question)])]

#     config = types.GenerateContentConfig(
#         system_instruction=SYSTEM_PROMPT,
#         tools=tools,
#         temperature=0.2,
#     )

#     response = client.models.generate_content(
#         model=MODEL_NAME,
#         contents=contents,
#         config=config,
#     )

#     while True:
#         candidate = response.candidates[0]

#         tool_calls = [
#             part.function_call
#             for part in candidate.content.parts
#             if getattr(part, "function_call", None)
#         ]

#         if not tool_calls:
#             update("finalizing", "Generating final response")
#             return response.text or ""

#         response_parts = []

#         for call in tool_calls:
#             if call.name in {"get_table_schema", "preview_rows", "run_sql", "ask_data_insights"}:
#                 update("analyzing", f"Using {call.name}")
#             elif call.name == "google_search":
#                 update("searching", "Searching Google")
#             elif call.name == "model_fallback":
#                 update("thinking", "Using Gemini fallback")

#             result = execute_tool_call(call.name, dict(call.args))

#             if call.name == "google_search":
#                 gs = result or {}
#                 results = gs.get("results", [])
#                 if not results:
#                     update("thinking", "Google Search empty; using Gemini fallback")
#                     result = {
#                         "source": "model_fallback_trigger",
#                         "reason": "Google Search returned no useful results.",
#                         "answer": model_fallback(user_question),
#                     }

#             response_parts.append(
#                 types.Part(
#                     function_response=types.FunctionResponse(
#                         name=call.name,
#                         response={"result": json_safe(result)},
#                     )
#                 )
#             )

#         contents.append(candidate.content)
#         contents.append(types.Content(role="tool", parts=response_parts))
#         update("thinking", "Refining answer")

#         response = client.models.generate_content(
#             model=MODEL_NAME,
#             contents=contents,
#             config=config,
#         )


# # -----------------------------------------------------------------------------
# # Flask routes
# # -----------------------------------------------------------------------------
# @app.route("/")
# def index():
#     """Render the chat page."""
#     history = session.get("history", [])
#     return render_template("index.html", history=history, table_id=FULL_TABLE_ID)


# @app.route("/chat", methods=["POST"])
# def chat():
#     """Receive a user message and start processing it in the background."""
#     data = request.get_json(force=True)
#     message = (data.get("message") or "").strip()

#     if not message:
#         return jsonify({"error": "Empty message"}), 400

#     chat_id = str(uuid.uuid4())

#     # Initialize the live state for this chat request
#     with STATE_LOCK:
#         CHAT_STATE[chat_id] = {
#             "status": "queued",
#             "detail": "Message received",
#             "done": False,
#             "answer": "",
#         }

#     # Save user message in session history
#     history = session.get("history", [])
#     history.append({"role": "user", "text": message})
#     session["history"] = history[-20:]
#     session.modified = True

#     # Background worker that performs analysis
#     def worker():
#         try:
#             def progress_cb(stage, detail):
#                 with STATE_LOCK:
#                     CHAT_STATE[chat_id]["status"] = stage
#                     CHAT_STATE[chat_id]["detail"] = detail

#             answer = analyze_question(message, progress_cb=progress_cb)

#             with STATE_LOCK:
#                 CHAT_STATE[chat_id]["status"] = "done"
#                 CHAT_STATE[chat_id]["detail"] = "Completed"
#                 CHAT_STATE[chat_id]["done"] = True
#                 CHAT_STATE[chat_id]["answer"] = answer

#         except Exception as e:
#             with STATE_LOCK:
#                 CHAT_STATE[chat_id]["status"] = "error"
#                 CHAT_STATE[chat_id]["detail"] = str(e)
#                 CHAT_STATE[chat_id]["done"] = True
#                 CHAT_STATE[chat_id]["answer"] = f"Error: {e}"

#     threading.Thread(target=worker, daemon=True).start()
#     return jsonify({"chat_id": chat_id})


# @app.route("/status/<chat_id>")
# def status(chat_id):
#     """Return live status for a chat request."""
#     with STATE_LOCK:
#         data = CHAT_STATE.get(
#             chat_id,
#             {"status": "missing", "detail": "Unknown chat id", "done": True, "answer": ""},
#         )
#     return jsonify(data)


# @app.route("/history/save", methods=["POST"])
# def save_history():
#     """Save assistant response into session history."""
#     data = request.get_json(force=True)
#     user_text = data.get("user_text", "")
#     assistant_text = data.get("assistant_text", "")

#     history = session.get("history", [])
#     if user_text:
#         history.append({"role": "user", "text": user_text})
#     if assistant_text:
#         history.append({"role": "assistant", "text": assistant_text})

#     session["history"] = history[-20:]
#     session.modified = True
#     return jsonify({"ok": True})


# @app.route("/clear", methods=["POST"])
# def clear():
#     """Clear the chat history."""
#     session.pop("history", None)
#     return jsonify({"ok": True})


# # -----------------------------------------------------------------------------
# # App entry point
# # -----------------------------------------------------------------------------
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)



#############################################################################################
#############################################################################################
## WITH TAVILY WEB SEARCH
#############################################################################################
#############################################################################################

import os
import json
import uuid
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List

import requests
from flask import Flask, render_template, request, jsonify, session
from google.cloud import bigquery
from google import genai
from google.genai import types
from tavily import TavilyClient

# -----------------------------------------------------------------------------
# Flask app setup
# -----------------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-me")

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PROJECT_ID = "gen-ai-ac"
DATASET_ID = "carbon1"
TABLE_ID = "tb-carbon"
FULL_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

MODEL_NAME = "gemini-2.5-flash"
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TAVILY_PROJECT_ID = os.getenv("TAVILY_PROJECT_ID", "")

# -----------------------------------------------------------------------------
# Shared in-memory chat state
# -----------------------------------------------------------------------------
CHAT_STATE: Dict[str, Dict[str, Any]] = {}
STATE_LOCK = threading.Lock()

# -----------------------------------------------------------------------------
# JSON-safe conversion helpers
# -----------------------------------------------------------------------------
def json_safe(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_safe(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_safe(v) for v in obj]
    return obj

def dumps_safe(obj: Any, **kwargs) -> str:
    return json.dumps(json_safe(obj), **kwargs)

# -----------------------------------------------------------------------------
# BigQuery sub-agent
# -----------------------------------------------------------------------------
class BigQuerySubAgent:
    def __init__(self, project_id: str, dataset_id: str, table_id: str):
        self.full_table_id = f"{project_id}.{dataset_id}.{table_id}"
        self.client = bigquery.Client(project=project_id)

    def get_table_schema(self) -> Dict[str, Any]:
        table = self.client.get_table(self.full_table_id)
        return json_safe({
            "table": self.full_table_id,
            "num_rows": table.num_rows,
            "num_columns": len(table.schema),
            "schema": [
                {
                    "name": f.name,
                    "type": f.field_type,
                    "mode": f.mode,
                    "description": f.description,
                }
                for f in table.schema
            ],
        })

    def preview_rows(self, limit: int = 10) -> List[Dict[str, Any]]:
        sql = f"SELECT * FROM `{self.full_table_id}` LIMIT {int(limit)}"
        rows = self.client.query(sql).result()
        return json_safe([dict(r.items()) for r in rows])

    def run_sql(self, sql: str, max_rows: int = 100) -> List[Dict[str, Any]]:
        rows = self.client.query(sql).result()
        return json_safe([dict(r.items()) for _, r in zip(range(max_rows), rows)])

    def ask_data_insights(self, question: str) -> Dict[str, Any]:
        schema = self.get_table_schema()
        sample = self.preview_rows(limit=10)
        return json_safe({
            "source": "bigquery",
            "table": self.full_table_id,
            "question": question,
            "schema": schema,
            "sample_rows": sample,
        })

# -----------------------------------------------------------------------------
# Tavily sub-agent
# -----------------------------------------------------------------------------
def tavily_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    if not TAVILY_API_KEY:
        return {
            "source": "tavily_search",
            "query": query,
            "results": [],
            "error": "Set TAVILY_API_KEY.",
        }

    try:
        client = TavilyClient(TAVILY_API_KEY)
        response = client.search(
            query=query,
            include_answer="basic",
            search_depth="advanced",
            max_results=min(max_results, 20),
        )

        results = []
        for item in response.get("results", [])[:max_results]:
            results.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score"),
                "published_date": item.get("published_date"),
                "favicon": item.get("favicon"),
            })

        return json_safe({
            "source": "tavily_search",
            "query": query,
            "answer": response.get("answer", ""),
            "results": results,
            "response_time": response.get("response_time"),
            "request_id": response.get("request_id"),
        })
    except Exception as e:
        return json_safe({
            "source": "tavily_search",
            "query": query,
            "results": [],
            "error": str(e),
        })

# -----------------------------------------------------------------------------
# Root agent initialization
# -----------------------------------------------------------------------------
bq_agent = BigQuerySubAgent(PROJECT_ID, DATASET_ID, TABLE_ID)
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# -----------------------------------------------------------------------------
# Tool declarations for Gemini function calling
# -----------------------------------------------------------------------------
tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_table_schema",
                description="Get BigQuery table schema and metadata.",
                parameters={"type": "object", "properties": {}},
            ),
            types.FunctionDeclaration(
                name="preview_rows",
                description="Preview rows from the BigQuery table.",
                parameters={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                },
            ),
            types.FunctionDeclaration(
                name="run_sql",
                description="Run SQL against the BigQuery table.",
                parameters={
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "max_rows": {"type": "integer", "default": 100},
                    },
                    "required": ["sql"],
                },
            ),
            types.FunctionDeclaration(
                name="ask_data_insights",
                description="Analyze the BigQuery table and return insight-oriented context.",
                parameters={
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            ),
            types.FunctionDeclaration(
                name="tavily_search",
                description="Search the web using Tavily when the answer is not found in BigQuery.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            ),
            types.FunctionDeclaration(
                name="model_fallback",
                description="Ask the Gemini model itself when both BigQuery and Tavily fail.",
                parameters={
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            ),
        ]
    )
]

# -----------------------------------------------------------------------------
# System prompt for root agent
# -----------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
You are the root agent for a data assistant.

Available sources:
1. BigQuery table `{FULL_TABLE_ID}`
2. Tavily Search fallback
3. Gemini model fallback when Tavily has no useful result

Decision policy:
- Prefer BigQuery for table-related, numeric, historical, or internal questions.
- If the answer is not present in the table, use tavily_search.
- If tavily_search returns no useful results or the question is general knowledge, use model_fallback.
- If the question is ambiguous, inspect schema or sample rows first.
- If neither source can answer, say what is missing.

Return short, direct answers.
"""

# -----------------------------------------------------------------------------
# Gemini model fallback
# -----------------------------------------------------------------------------
def model_fallback(question: str) -> str:
    resp = client.models.generate_content(
        model=MODEL_NAME,
        contents=[types.Content(role="user", parts=[types.Part(text=question)])],
        config=types.GenerateContentConfig(temperature=0.2),
    )
    return resp.text or ""

# -----------------------------------------------------------------------------
# Tool execution router
# -----------------------------------------------------------------------------
def execute_tool_call(name: str, args: Dict[str, Any]) -> Any:
    if name == "get_table_schema":
        return bq_agent.get_table_schema()
    if name == "preview_rows":
        return bq_agent.preview_rows(limit=args.get("limit", 10))
    if name == "run_sql":
        return bq_agent.run_sql(sql=args["sql"], max_rows=args.get("max_rows", 100))
    if name == "ask_data_insights":
        return bq_agent.ask_data_insights(question=args["question"])
    if name == "tavily_search":
        return tavily_search(query=args["query"], max_results=args.get("max_results", 5))
    if name == "model_fallback":
        return {"source": "model_fallback", "answer": model_fallback(args["question"])}
    raise ValueError(f"Unknown tool: {name}")

# -----------------------------------------------------------------------------
# Main reasoning function
# -----------------------------------------------------------------------------
def analyze_question(user_question: str, progress_cb=None) -> str:
    def update(stage: str, detail: str = ""):
        if progress_cb:
            progress_cb(stage, detail)

    update("thinking", "Preparing answer")

    contents = [types.Content(role="user", parts=[types.Part(text=user_question)])]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        temperature=0.2,
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=contents,
        config=config,
    )

    while True:
        candidate = response.candidates[0]

        tool_calls = [
            part.function_call
            for part in candidate.content.parts
            if getattr(part, "function_call", None)
        ]

        if not tool_calls:
            update("finalizing", "Generating final response")
            return response.text or ""

        response_parts = []

        for call in tool_calls:
            if call.name in {"get_table_schema", "preview_rows", "run_sql", "ask_data_insights"}:
                update("analyzing", f"Using {call.name}")
            elif call.name == "tavily_search":
                update("searching", "Searching Web")
            elif call.name == "model_fallback":
                update("thinking", "Using Gemini fallback")

            result = execute_tool_call(call.name, dict(call.args))

            if call.name == "tavily_search":
                tv = result or {}
                results = tv.get("results", [])
                if not results:
                    update("thinking", "Tavily empty; using Gemini fallback")
                    result = {
                        "source": "model_fallback_trigger",
                        "reason": "Tavily returned no useful results.",
                        "answer": model_fallback(user_question),
                    }

            response_parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        name=call.name,
                        response={"result": json_safe(result)},
                    )
                )
            )

        contents.append(candidate.content)
        contents.append(types.Content(role="tool", parts=response_parts))
        update("thinking", "Refining answer")

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )

# -----------------------------------------------------------------------------
# Flask routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    history = session.get("history", [])
    return render_template("index.html", history=history, table_id=FULL_TABLE_ID)

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    message = (data.get("message") or "").strip()

    if not message:
        return jsonify({"error": "Empty message"}), 400

    chat_id = str(uuid.uuid4())

    with STATE_LOCK:
        CHAT_STATE[chat_id] = {
            "status": "queued",
            "detail": "Message received",
            "done": False,
            "answer": "",
        }

    history = session.get("history", [])
    history.append({"role": "user", "text": message})
    session["history"] = history[-20:]
    session.modified = True

    def worker():
        try:
            def progress_cb(stage, detail):
                with STATE_LOCK:
                    CHAT_STATE[chat_id]["status"] = stage
                    CHAT_STATE[chat_id]["detail"] = detail

            answer = analyze_question(message, progress_cb=progress_cb)

            with STATE_LOCK:
                CHAT_STATE[chat_id]["status"] = "done"
                CHAT_STATE[chat_id]["detail"] = "Completed"
                CHAT_STATE[chat_id]["done"] = True
                CHAT_STATE[chat_id]["answer"] = answer

        except Exception as e:
            with STATE_LOCK:
                CHAT_STATE[chat_id]["status"] = "error"
                CHAT_STATE[chat_id]["detail"] = str(e)
                CHAT_STATE[chat_id]["done"] = True
                CHAT_STATE[chat_id]["answer"] = f"Error: {e}"

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"chat_id": chat_id})

@app.route("/status/<chat_id>")
def status(chat_id):
    with STATE_LOCK:
        data = CHAT_STATE.get(
            chat_id,
            {"status": "missing", "detail": "Unknown chat id", "done": True, "answer": ""},
        )
    return jsonify(data)

@app.route("/history/save", methods=["POST"])
def save_history():
    data = request.get_json(force=True)
    user_text = data.get("user_text", "")
    assistant_text = data.get("assistant_text", "")

    history = session.get("history", [])
    if user_text:
        history.append({"role": "user", "text": user_text})
    if assistant_text:
        history.append({"role": "assistant", "text": assistant_text})

    session["history"] = history[-20:]
    session.modified = True
    return jsonify({"ok": True})

@app.route("/clear", methods=["POST"])
def clear():
    session.pop("history", None)
    return jsonify({"ok": True})

# -----------------------------------------------------------------------------
# App entry point
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)