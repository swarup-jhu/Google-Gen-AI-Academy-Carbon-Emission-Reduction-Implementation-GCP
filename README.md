## BigQuery - Gemini-2.5-Flash - Flask Chatbot - Carbon Emission Reduction Application for Google GEN AI Academy – Implementation On Google Cloud

A Flask-based chatbot that answers questions using a tiered intelligence pipeline:

1. BigQuery for structured data and table-aware questions.
2. Tavily Search for web fallback when the table has no answer.
3. Gemini as the final fallback when web search is not enough.

The app also provides live progress updates in the chat UI, including states like `thinking`, `analyzing`, `searching`, and `finalizing`.

---

## Overview

This project is designed as a retrieval-augmented chatbot for a BigQuery dataset. It uses Gemini function calling to decide whether it should inspect the table schema, preview rows, run SQL, search the web, or fall back to the model itself.

The current code is configured to work with the BigQuery table `gen-ai-ac.carbon1.tb-carbon`, but you can point it to any other table by changing the constants in the app.

---

## Key Features

- Flask web app with a chat-based interface.
- BigQuery integration for schema lookup, row preview, and SQL execution.
- Tavily web search fallback.
- Gemini model fallback for unanswered questions.
- Live request status polling through `/status/<chat_id>`.
- Session-based chat history.
- JSON-safe conversion for dates, datetimes, and decimals.
- Background thread processing for each chat request.

---

## Architecture

The assistant follows a simple decision chain:

1. Use BigQuery first for:
   - table-related questions,
   - numeric analysis,
   - historical data,
   - internal dataset questions.

2. Use Tavily Search if the answer is not available in the table.

3. Use Gemini fallback if Tavily returns no useful results or the question is general knowledge.

This gives the app both structured-data strength and general web reasoning capability 

---

## Tech Stack

- Backend: Flask
- Database: Google BigQuery
- Web Search: Tavily
- LLM: Gemini via Google Gen AI SDK
- HTTP Requests: requests
- Concurrency: Python threading

---

If your project uses a different structure, keep the same separation between backend code, templates, and static files.

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

On Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install Flask requests google-cloud-bigquery google-genai tavily-python
```

The BigQuery Python client is the official library used for querying tables and reading table metadata [page:2]. Tavily’s API supports search queries, answer generation, search depth, and structured result metadata such as title, URL, content, and score [page:1].

---

## Environment Variables

Create a `.env` file in the project root:

```env
FLASK_SECRET_KEY=your-secret-key
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GOOGLE_CLOUD_LOCATION=us-central1
TAVILY_API_KEY=your-tavily-api-key
```
Flask generally works without api key. 
Download GOOGLE_APPLICATION_CREDENTIALS after allowing all necessary roles to Compute Engine Service as a json file and save it locally. Mention the json file while creating DOCKER container. 

### Variable Details

- `FLASK_SECRET_KEY`: Secures Flask sessions.
- `GOOGLE_APPLICATION_CREDENTIALS`: Path to your Google service account JSON file.
- `GOOGLE_CLOUD_LOCATION`: Vertex AI region for Gemini.
- `TAVILY_API_KEY`: Enables web search fallback.

---

## Running Locally

Start the application with:

```bash
python agent.py
```

The app runs on port `5000` by default as in agent.py, or the value in the `PORT` environment variable if set any.

Open the app in your browser and send a message through the chat UI.

But default port in GCP is 8080. If you use any other port, update in GCP. 

---

## How It Works

### 1. User submits a message
The `/chat` endpoint receives the user message and starts a background worker thread.

### 2. Status is initialized
A unique `chat_id` is generated and stored in the in-memory `CHAT_STATE` dictionary.

### 3. Gemini decides which tool to use
The root agent is configured with Gemini function declarations for:
- table schema lookup,
- row preview,
- SQL execution,
- BigQuery analysis,
- Tavily web search,
- Gemini fallback.

### 4. Tool results are returned to Gemini
The app executes the requested tool and passes the result back into the model.

### 5. Final answer is produced
Once no more tool calls are needed, the model returns the final response.

---

## Available Endpoints

### `GET /`
Renders the chat page and loads session history.

### `POST /chat`
Accepts a JSON payload:

```json
{
  "message": "What does the dataset say about emissions?"
}
```

Returns:

```json
{
  "chat_id": "uuid-here"
}
```

### `GET /status/<chat_id>`
Returns live status for the request:

```json
{
  "status": "searching",
  "detail": "Searching Web",
  "done": false,
  "answer": ""
}
```

### `POST /history/save`
Saves user and assistant messages into the session history.

### `POST /clear`
Clears the current chat history.

---

## BigQuery Functions

The `BigQuerySubAgent` class provides these methods:

### `get_table_schema()`
Returns:
- table name,
- row count,
- column count,
- full schema with field metadata.

### `preview_rows(limit=10)`
Returns a small sample of rows from the target table.

### `run_sql(sql, max_rows=100)`
Runs SQL against the target BigQuery table and returns rows.

### `ask_data_insights(question)`
Builds structured context from schema and sample rows so the model can reason about the dataset.

---

## Tavily Search Fallback

The `tavily_search()` function is used when BigQuery does not contain the answer.

It:
- sends the query to Tavily,
- requests a basic answer,
- uses advanced search depth,
- returns top results with metadata.

If Tavily returns no useful results, the app automatically falls back to Gemini.

---

## Gemini Fallback

The `model_fallback()` function calls Gemini directly when both:
- BigQuery does not help, and
- Tavily Search is empty or not relevant.

This ensures the app can still answer general knowledge questions.

---

## Live Status States

The app uses these progress states:

- `queued`
- `thinking`
- `analyzing`
- `searching`
- `finalizing`
- `done`
- `error`

These states are stored in memory and can be fetched from the `/status/<chat_id>` endpoint while the request is being processed.

---

## Example Questions

Try questions like:

- “Show me the schema of the carbon table.”
- “Give me a preview of the dataset.”
- “What SQL can summarize emissions by month?”
- "What is total carbon emission for our shipment of last month? ”
- "Show total carbon emission for our last mile delivery." 
- “Find recent articles about carbon reporting.”

The first set should favor BigQuery, while general knowledge questions can fall back to Tavily and Gemini.

---

## Error Handling

The app handles common failure modes such as:
- missing API keys,
- BigQuery authentication problems,
- Tavily search failures,
- Gemini fallback errors,
- malformed or empty chat input.

When an error occurs, the `/status/<chat_id>` response is updated with an `error` state and the exception message.

---

## Security Notes

- Never commit `.env` or service account files to GitHub.
- Keep `API-KEY` private.
- Use a production WSGI server for deployment instead of Flask’s debug server.

---

## Deployment

Recommended deployment checklist:
- set environment variables in the hosting platform,
- disable debug mode,
- ensure BigQuery permissions are correct,
- ensure Tavily API access is enabled,
- confirm Vertex AI/Gemini region access.

---

## Requirements

```txt
Flask
requests
google-cloud-bigquery
google-genai
tavily-python
```

Optional but useful:

```txt
python-dotenv
gunicorn
```

---

## Future Improvements

- Persistent conversation storage.
- Streaming responses instead of polling.
- SQL query guardrails for safer execution.
- Better frontend loading indicators.
- Charts and summaries for query results.
- Multi-table support.
- User authentication.

---

## License

Add your preferred license here, such as MIT or Apache 2.0.

---

## Acknowledgments

- Google BigQuery for structured data access.
- Tavily for web search and answer retrieval.
- Gemini for model fallback and reasoning.


