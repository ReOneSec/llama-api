# llama-api
Secure, Streaming LLaMA FastAPI Backend
This project provides a robust, secure, and feature-rich FastAPI backend to interact with a local LLaMA-based Large Language Model (LLM) using the llama-cli tool from llama.cpp.
It's designed for local use but includes security and observability features like API key authentication, rate limiting, and Prometheus metrics, making it a powerful foundation for more advanced applications.
✨ Key Features
 * 🚀 Real-time Streaming: Get responses from the LLM token-by-token for a highly interactive user experience.
 * 🧠 Stateful Conversations: Maintains persistent chat history for each user/session, providing context to the model.
 * 🔒 Robust Security:
   * API Key Authentication: Protects all endpoints with an X-API-Key header.
   * Rate Limiting: IP-based rate limiting (20 chats/hour) to prevent abuse.
   * Input Sanitization: Protects against path traversal vulnerabilities.
   * Concurrency Control: Uses file locks to prevent data corruption from simultaneous requests.
 * 📊 Observability:
   * Structured Logging: Detailed logging with levels for clear operational insight.
   * Health Endpoint: A /health endpoint for uptime checks.
   * Prometheus Metrics: A /metrics endpoint for performance monitoring.
 * ⚙️ Configuration & Debugging:
   * System Prompts: Set a custom system prompt to guide the model's personality and behavior.
   * Dry Run Mode: A dry_run=true flag on the chat endpoint to see the exact prompt sent to the model.
 * 🗂️ Full Chat Management: API endpoints to list, retrieve, and delete chat histories.
🔧 Prerequisites
Before you begin, ensure you have the following installed and configured:
 * Python 3.10+
 * llama.cpp: You must have llama.cpp compiled on your system. This project calls the llama-cli executable directly. You can find instructions at the official llama.cpp repository.
 * A GGUF Model File: A LLaMA-based model in GGUF format (e.g., zephyr.gguf).
⚙️ Setup & Installation
 * Clone the Repository
   git clone <your-repository-url>
cd <your-repository-directory>

 * Create a requirements.txt File
   Create a file named requirements.txt with the following content:
   fastapi
uvicorn[standard]
pydantic
slowapi
prometheus-fastapi-instrumentator

 * Install Dependencies
   pip install -r requirements.txt

 * Configure main.py
   This is the most important step. Open the main.py file and update the configuration constants at the top:
   # --- Application Configuration ---
LLAMA_CLI_PATH = "/path/to/your/llama.cpp/build/bin/llama-cli"
MODEL_PATH = "/path/to/your/models/your-model.gguf"

# --- Security & Rate Limiting ---
# ⚠️ IMPORTANT: Change this key for any non-local deployment!
SECRET_API_KEY = "your-super-secret-key" 

▶️ Running the Application
Once configured, you can run the application using uvicorn:
uvicorn main:app --reload --host 0.0.0.0 --port 8000

 * --reload: The server will automatically restart when you make changes to the code.
 * The API will be available at http://localhost:8000.
📚 API Documentation
All endpoints require the X-API-Key header for authentication.
Core
<hr>
POST /chat
Starts a new chat or continues an existing one, streaming the response.
 * Query Parameter: dry_run=true (optional) - Returns the generated prompt instead of executing it.
 * Headers: X-API-Key: your-super-secret-key
 * Body:
   {
  "message": "What is the capital of India?",
  "chat_id": "user123_session_1"
}

 * cURL Example:
   curl -N -X POST http://localhost:8000/chat \
-H "Content-Type: application/json" \
-H "X-API-Key: your-super-secret-key" \
-d '{
  "message": "What is the capital of India?",
  "chat_id": "user123_session_1"
}'

 * Success Response: A text/plain stream of tokens from the LLM.
History Management
<hr>
GET /chats
Lists the IDs of all available chat sessions.
 * cURL Example:
   curl -X GET http://localhost:8000/chats -H "X-API-Key: your-super-secret-key"

 * Success Response:
   {
  "chat_ids": ["user123_session_1", "default"]
}

GET /history/{chat_id}
Retrieves the full conversation data for a specific chat_id.
 * cURL Example:
   curl -X GET http://localhost:8000/history/user123_session_1 -H "X-API-Key: your-super-secret-key"

 * Success Response:
   {
  "system_prompt": null,
  "history": [
    {
      "user": "What is the capital of India?",
      "assistant": "New Delhi is the capital of India."
    }
  ]
}

POST /history/{chat_id}/system_prompt
Sets or updates the system prompt for a chat session.
 * cURL Example:
   curl -X POST http://localhost:8000/history/user123_session_1/system_prompt \
-H "Content-Type: application/json" \
-H "X-API-Key: your-super-secret-key" \
-d '{"system_prompt": "You are a helpful assistant that always responds in rhymes."}'

DELETE /history/{chat_id}
Deletes the entire history for a specific chat_id.
 * cURL Example:
   curl -X DELETE http://localhost:8000/history/user123_session_1 -H "X-API-Key: your-super-secret-key"

 * Success Response:
   {
  "detail": "Chat history 'user123_session_1' deleted."
}

Monitoring
<hr>
GET /health
A simple health check endpoint.
 * cURL Example:
   curl http://localhost:8000/health

 * Response: {"status": "ok"}
GET /metrics
Exposes Prometheus metrics for monitoring API performance.
 * cURL Example:
   curl http://localhost:8000/metrics

⚖️ License
This project is licensed under the MIT License. See the LICENSE file for details.
