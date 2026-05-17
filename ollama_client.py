"""
ollama_client.py
Handles all communication with the local Ollama instance (qwen3:latest).
Returns structured JSON that the Flask app acts on.
"""

import requests
import json
import re
import logging

OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL_NAME  = "qwen3:latest"

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an Order Management AI assistant for a manufacturing company.
Your ONLY job is to parse the user's message and return a single, valid JSON object.

Supported actions and their required JSON fields:

1. Create a new order:
   {"action":"create_order","part":"<name>","material":"<material>","quantity":<int>,"deadline":"<YYYY-MM-DD>"}

2. Update order status (valid statuses: Pending, Accepted, Rejected, In Progress, Completed):
   {"action":"update_status","order_id":<int>,"status":"<status>"}

3. Add a quality inspection note:
   {"action":"add_quality_log","order_id":<int>,"note":"<note text>"}

4. Query a specific order:
   {"action":"query_order","order_id":<int>}

5. List orders (filter: "all", "pending", "accepted", "rejected", "in progress", "completed"):
   {"action":"list_orders","filter":"<filter>"}

6. General conversation / unknown intent:
   {"action":"unknown","reply":"<your helpful response>"}

Rules:
- ALWAYS return ONLY the JSON object — no markdown fences, no extra text.
- If a date is missing, use today's date + 30 days.
- If quantity is missing, use 1.
- If material is missing, use "Not specified".
- Extract order IDs from phrases like "order #5", "order number 3", "the third order".
- For status updates, map natural language: "accept" → "Accepted", "reject" → "Rejected",
  "start" / "begin" → "In Progress", "finish" / "done" / "complete" → "Completed".
"""


def parse_json_from_response(text: str) -> dict:
    """Extract and parse the first JSON object found in the model's response."""
    # Strip thinking tags (qwen3 uses <think>...</think>)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from response: %s", text[:200])
    return {"action": "unknown", "reply": text or "I couldn't understand that request."}


def chat(user_message: str) -> dict:
    """
    Send a user message to Ollama and return the parsed action dict.
    Raises ConnectionError if Ollama is not running.
    """
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}\n\nJSON:"

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,   # Low temp = deterministic JSON
                    "num_predict": 512,
                }
            },
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data.get("response", "")
        logger.debug("Raw Ollama response: %s", raw_text)
        return parse_json_from_response(raw_text)

    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            "Cannot connect to Ollama. Make sure it's running: `ollama serve`"
        )
    except requests.exceptions.Timeout:
        raise TimeoutError("Ollama took too long to respond. Try again.")
    except Exception as e:
        logger.exception("Unexpected Ollama error")
        raise RuntimeError(f"Ollama error: {e}")
