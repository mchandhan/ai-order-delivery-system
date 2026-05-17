"""
gemini_client.py
Uses Google Gemini 2.0 Flash via REST API — fast (~1-2s), free tier available.
Get your key at: https://aistudio.google.com/app/apikey
"""

import os
import re
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-1.5-flash"

def get_api_key():
    """Retrieve the API key from environment."""
    return os.getenv("GEMINI_API_KEY", "").strip()

def get_gemini_url():
    """Construct the URL with the current API key."""
    return (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={get_api_key()}"
    )

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
- Return ONLY the raw JSON object — no markdown, no code fences, no explanation.
- If deadline is missing, use today + 30 days.
- If quantity is missing, use 1.
- If material is missing, use "Not specified".
- Extract order IDs from "order #5", "order number 3", "order 2", etc.
- Map natural language status: "accept"→"Accepted", "reject"→"Rejected",
  "start"/"begin"→"In Progress", "finish"/"done"/"complete"→"Completed".
"""


def parse_json(text: str) -> dict:
    """Strip markdown fences and parse the first JSON object found."""
    # Remove ```json ... ``` fences if Gemini wraps output
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    logger.warning("Could not parse JSON: %s", text[:200])
    return {"action": "unknown", "reply": text or "I couldn't understand that request."}


def chat(user_message: str) -> dict:
    """Send message to Gemini and return parsed action dict."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not set. Add it to your .env file.\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )

    full_prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_message}\n\nJSON:"

    payload = {
        "contents": [
            {"parts": [{"text": full_prompt}]}
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 256,
            # Removed responseMimeType to improve compatibility
        }
    }

    # Simple retry logic for rate limits
    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = requests.post(
                get_gemini_url(),
                json=payload,
                timeout=15
            )
            
            # Handle 429 specifically for retry
            if response.status_code == 429 and attempt < max_retries - 1:
                logger.warning("Rate limit hit, retrying in 2 seconds...")
                import time
                time.sleep(2)
                continue
                
            response.raise_for_status()
            
            data = response.json()
            raw_text = (
                data.get("candidates", [{}])[0]
                    .get("content", {})
                    .get("parts", [{}])[0]
                    .get("text", "")
            )
            logger.debug("Gemini raw: %s", raw_text)
            return parse_json(raw_text)

        except requests.exceptions.ConnectionError:
            raise ConnectionError("Cannot reach Gemini API. Check your internet connection.")
        except requests.exceptions.Timeout:
            raise TimeoutError("Gemini API timed out. Please try again.")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            # Retry 429 from HTTPError as well
            if status == 429 and attempt < max_retries - 1:
                import time
                time.sleep(2)
                continue
            
            if status == 400:
                raise ValueError("Bad request to Gemini — check your API key or prompt.")
            elif status == 403:
                raise PermissionError("Invalid or expired Gemini API key.")
            elif status == 429:
                raise RuntimeError("Gemini rate limit hit. Wait a moment and retry.")
            raise RuntimeError(f"Gemini HTTP error {status}: {e}")
        except Exception as e:
            logger.exception("Unexpected Gemini error")
            raise RuntimeError(f"Gemini error: {e}")

    return {"action": "unknown", "reply": "Failed to get a response from AI after retries."}
