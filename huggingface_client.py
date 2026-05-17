"""
huggingface_client.py
Uses Hugging Face Router (OpenAI-compatible) for high-performance models.
"""

import os
import re
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BASE_URL = "https://router.huggingface.co/v1"
MODEL_NAME = "deepseek-ai/DeepSeek-V4-Pro:novita"

def get_client():
    """Lazily initialize the OpenAI client, reloading .env if needed."""
    # Force load from the current directory to be sure
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    token = os.getenv("HF_API_TOKEN", "").strip()
    
    if not token:
        load_dotenv(env_path, override=True)
        token = os.getenv("HF_API_TOKEN", "").strip()
        
    if not token:
        # Diagnostic: print the path we tried to load
        print(f"DEBUG: Tried loading .env from: {os.path.abspath(env_path)}")
        raise ValueError(f"HF_API_TOKEN is not set in your .env file at {env_path}")
        
    return OpenAI(
        base_url=BASE_URL,
        api_key=token,
    )

SYSTEM_PROMPT = """Order AI Assistant. Return JSON ONLY. No text/markdown.
Schema:
- Create: {"action":"create_order","part":"<name>","material":"<mat>","quantity":<int>,"deadline":"<YYYY-MM-DD>"}
- Status: {"action":"update_status","order_id":<int>,"status":"Received|In Review|Accepted|Completed|Rejected"}
- Log: {"action":"add_quality_log","order_id":<int>,"note":"<note>"}
- Query: {"action":"query_order","order_id":<int>}
- List: {"action":"list_orders","filter":"all|received|in review|accepted|completed|rejected"}
- Other: {"action":"unknown","reply":"<response>"}
Rules:
- Quantity default: 1. Material default: Not specified.
- No fences or explanation.
"""

def parse_json(text: str) -> dict:
    """Extract JSON from the model response."""
    # Remove markdown fences if the model includes them
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Fallback: extract the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
            
    logger.warning("Could not parse JSON: %s", text[:200])
    return {"action": "unknown", "reply": text or "I couldn't understand that request."}

def chat(user_message: str) -> dict:
    """Send message to DeepSeek via HF Router."""
    try:
        client = get_client()
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            temperature=0.1,
            max_tokens=512
        )

        raw_text = completion.choices[0].message.content
        logger.debug("AI Response: %s", raw_text)
        return parse_json(raw_text)

    except Exception as e:
        logger.exception("HF Router Error")
        raise RuntimeError(f"AI Router error: {e}")
