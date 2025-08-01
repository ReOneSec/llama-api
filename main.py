import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Dict, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, constr
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Application Configuration ---
LLAMA_CLI_PATH = "/home/viper/llama.cpp/build/bin/llama-cli"
MODEL_PATH = "/home/viper/llama.cpp/models/zephyr/zephyr.gguf"
HISTORY_DIR = "chat_history"
MAX_HISTORY_MESSAGES = 10
MAX_INPUT_LENGTH = 2048
MAX_TOTAL_CHATS = 100

os.makedirs(HISTORY_DIR, exist_ok=True)

# --- Security & Rate Limiting ---
SECRET_API_KEY = "your-secret-key-here"  # ⚠️ IMPORTANT: Change this!
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
limiter = Limiter(key_func=get_remote_address)
chat_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

async def get_api_key(api_key: str = Security(API_KEY_HEADER)):
    if SECRET_API_KEY == "your-secret-key-here":
        logger.warning("Running with the default API key. The application is insecure.")
        return
    if api_key == SECRET_API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Could not validate credentials")

# --- Pydantic Models ---
SafeStr = constr(strip_whitespace=True, min_length=1, max_length=MAX_INPUT_LENGTH)
SafeChatID = constr(strip_whitespace=True, min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')

class ChatRequest(BaseModel):
    message: SafeStr
    chat_id: SafeChatID = "default"

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Full-Featured LLM Backend",
    description="An advanced, streaming-capable API for local LLMs via llama-cli.",
    version="1.1.1", # Incremented version for the fix
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
Instrumentator().instrument(app).expose(app)


# --- Middleware for Attribution Header ---
@app.middleware("http")
async def add_creator_header(request: Request, call_next):
    response = await call_next(request)
    # [FIX] Use an ASCII-safe alternative for the heart emoji to prevent encoding errors
    response.headers["X-Creator"] = "Made With <3 By SAHABAJ"
    return response


# --- Helper Functions ---
def get_sanitized_history_path(chat_id: SafeChatID) -> str:
    return os.path.join(HISTORY_DIR, f"{chat_id}.json")

def load_chat_data(chat_id: SafeChatID) -> dict:
    history_file = get_sanitized_history_path(chat_id)
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            return json.load(f)
    return {"system_prompt": None, "history": []}

def save_chat_data(chat_id: SafeChatID, data: dict):
    history_file = get_sanitized_history_path(chat_id)
    with open(history_file, "w") as f:
        json.dump(data, f, indent=2)

# --- Core Streaming Logic ---
async def stream_llama_response(chat_request: ChatRequest):
    lock = chat_locks[chat_request.chat_id]
    async with lock:
        chat_data = load_chat_data(chat_request.chat_id)

    system_prompt, chat_history = chat_data.get("system_prompt"), chat_data.get("history", [])[-MAX_HISTORY_MESSAGES:]
    prompt_parts = []
    if system_prompt:
        logger.info(f"Using system prompt for chat_id '{chat_request.chat_id}'")
        prompt_parts.append(system_prompt)

    for turn in chat_history:
        prompt_parts.append(f"### Human: {turn['user']}\n### Assistant: {turn['assistant']}")
    prompt_parts.append(f"### Human: {chat_request.message}\n### Assistant:")
    full_prompt = "\n".join(prompt_parts)

    command = [LLAMA_CLI_PATH, "-m", MODEL_PATH, "--prompt", full_prompt, "-n", "-1"]
    process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    
    full_response_bytes = b''
    if process.stdout:
        while not process.stdout.at_eof():
            token = await process.stdout.read(1)
            if not token: break
            full_response_bytes += token
            yield token
    await process.wait()

    if process.returncode != 0:
        stderr = (await process.stderr.read()).decode('utf-8', 'ignore').strip()
        error_message = f"\n\n[ERROR] Model execution failed. Details:\n{stderr}\n"
        logger.error(f"LLM process failed for chat_id '{chat_request.chat_id}': {stderr}")
        yield error_message.encode('utf-8')
        return

    assistant_response = full_response_bytes.decode('utf-8', 'ignore').split("### Assistant:")[-1].strip()
    if not assistant_response:
        logger.warning(f"LLM generated an empty response for chat_id '{chat_request.chat_id}'. History will not be updated.")
        return

    async with lock:
        final_chat_data = load_chat_data(chat_request.chat_id)
        final_chat_data["history"].append({"user": chat_request.message, "assistant": assistant_response})
        final_chat_data["history"] = final_chat_data["history"][-MAX_HISTORY_MESSAGES:]
        save_chat_data(chat_request.chat_id, final_chat_data)
        logger.info(f"History updated for chat_id: '{chat_request.chat_id}'")


# --- API Endpoints ---
@app.get("/", tags=["General"])
async def read_root():
    """Provides a welcome message."""
    return {"message": "Welcome to the Secure LLM Backend API!"}

@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Provides a simple health check for uptime monitoring."""
    return {"status": "ok"}

@app.post("/chat", tags=["Core"])
@limiter.limit("20/hour")
async def chat(request: Request, chat_request: ChatRequest, dry_run: bool = False, api_key: str = Depends(get_api_key)):
    """Main chat endpoint. Streams the LLM response and enforces rate limits."""
    log_extra = f"(Dry Run)" if dry_run else ""
    logger.info(f"Chat request for '{chat_request.chat_id}' from IP: {request.client.host} {log_extra}")

    history_path = get_sanitized_history_path(chat_request.chat_id)
    is_new_chat = not os.path.exists(history_path)

    if is_new_chat:
        logger.info(f"Creating new chat history for chat_id: '{chat_request.chat_id}'")
        if len(os.listdir(HISTORY_DIR)) >= MAX_TOTAL_CHATS:
            raise HTTPException(status_code=429, detail="The maximum number of chat sessions has been reached.")
    else:
        logger.info(f"Reusing existing chat history for chat_id: '{chat_request.chat_id}'")

    if dry_run:
        chat_data = load_chat_data(chat_request.chat_id)
        system_prompt, chat_history = chat_data.get("system_prompt"), chat_data.get("history", [])[-MAX_HISTORY_MESSAGES:]
        prompt_parts = []
        if system_prompt: prompt_parts.append(system_prompt)
        for turn in chat_history:
            prompt_parts.append(f"### Human: {turn['user']}\n### Assistant: {turn['assistant']}")
        prompt_parts.append(f"### Human: {chat_request.message}\n### Assistant:")
        return PlainTextResponse("\n".join(prompt_parts))
        
    return StreamingResponse(stream_llama_response(chat_request), media_type="text/plain")

@app.get("/chats", tags=["History Management"])
async def list_chats(api_key: str = Depends(get_api_key)):
    """Lists all available chat session IDs."""
    logger.info("Chat list requested.")
    try:
        files = [f for f in os.listdir(HISTORY_DIR) if f.endswith(".json")]
        chat_ids = [os.path.splitext(f)[0] for f in files]
        return {"chat_ids": chat_ids}
    except OSError as e:
        logger.error(f"Failed to list chats in '{HISTORY_DIR}': {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve chat list.")

@app.get("/history/{chat_id}", tags=["History Management"])
async def get_history(chat_id: SafeChatID, api_key: str = Depends(get_api_key)):
    """Retrieves the full conversation data for a given chat_id."""
    logger.info(f"History requested for chat_id: '{chat_id}'")
    history_file = get_sanitized_history_path(chat_id)
    if not os.path.exists(history_file):
        raise HTTPException(status_code=404, detail="Chat history not found.")
    return load_chat_data(chat_id)

@app.delete("/history/{chat_id}", tags=["History Management"])
async def delete_history(chat_id: SafeChatID, api_key: str = Depends(get_api_key)):
    """Safely deletes the conversation history for a given chat_id."""
    logger.info(f"Delete request for chat_id: '{chat_id}'")
    lock = chat_locks[chat_id]
    async with lock:
        history_file = get_sanitized_history_path(chat_id)
        if not os.path.exists(history_file):
            logger.warning(f"Attempted to delete non-existent history for chat_id: '{chat_id}'")
            raise HTTPException(status_code=404, detail="Chat history not found.")
        try:
            os.remove(history_file)
            logger.info(f"History deleted for chat_id: '{chat_id}'")
            return {"detail": f"Chat history '{chat_id}' deleted."}
        except OSError as e:
            logger.error(f"Failed to delete '{history_file}': {e}")
            raise HTTPException(status_code=500, detail="Failed to delete history file.")
