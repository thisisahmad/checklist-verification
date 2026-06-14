"""OpenAI integration layer for explainable compliance verification.

This file contains functions that:
- call OpenAI ChatCompletion for explainable verification,
- call OpenAI embeddings for semantic similarity (optional),
- provide higher-level helpers that use the LLM to reason about a rule and a document.

You MUST set OPENAI_API_KEY in environment or .env before running.
"""
import os
import json
from dotenv import load_dotenv
from app_logging import get_logger

load_dotenv()
OPENAI_KEY = os.getenv('OPENAI_API_KEY')
logger = get_logger("openai")


def _as_text(value):
    if value is None:
        return ''
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _get_openai_client():
    try:
        from openai import OpenAI
        # If OPENAI_KEY is None, the OpenAI client will read from env as well
        client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else OpenAI()
        return client
    except Exception as e:
        raise RuntimeError(f"OpenAI python package not available: {e}")

def call_openai_chat(system_prompt, user_prompt, model='gpt-5', max_tokens=900, temperature=0.0):
    client = _get_openai_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    params = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    if model.startswith("gpt-5") or model.startswith("o"):
        params["max_completion_tokens"] = max_tokens
    else:
        params["max_tokens"] = max_tokens

    logger.debug("OpenAI request | model=%s | params=%s", model, list(params.keys()))
    for attempt in range(4):
        try:
            resp = client.chat.completions.create(**params)
            logger.info("OpenAI response OK | model=%s | attempt=%s", model, attempt + 1)
            return resp.choices[0].message.content
        except Exception as e:
            message = str(e)
            if "Unsupported parameter" not in message:
                logger.error("OpenAI request failed | model=%s | error=%s", model, message)
                raise
            logger.warning(
                "OpenAI parameter retry | model=%s | attempt=%s | error=%s",
                model,
                attempt + 1,
                message[:200],
            )
            params.pop("response_format", None)
            if "max_tokens" in message:
                params.pop("max_tokens", None)
                params["max_completion_tokens"] = max_tokens
            elif "max_completion_tokens" in message:
                params.pop("max_completion_tokens", None)
                params["max_tokens"] = max_tokens
            elif "temperature" in message:
                params.pop("temperature", None)
            else:
                raise
    resp = client.chat.completions.create(**params)
    return resp.choices[0].message.content

def call_embeddings(texts, model='text-embedding-3-large'):
    client = _get_openai_client()
    if isinstance(texts, str):
        texts = [texts]
    resp = client.embeddings.create(model=model, input=texts)
    return [r.embedding for r in resp.data]

def explain_verification(rule, document_snippet, model='gpt-5'):
    system_prompt = (
        "You are a senior compliance verification analyst. Evaluate whether the document "
        "satisfies the checklist rule using only the provided excerpt. Be strict, evidence-based, "
        "and useful for audit review.\n"
        "Return JSON only with these keys: outcome (PASS/PARTIAL/FAIL), confidence (0.0-1.0), "
        "explanation, evidence, missing_info, recommendation. Keep each value concise but specific."
    )
    user_prompt = (
        f"Rule:\n{json.dumps(rule, indent=2)}\n\n"
        f"Document excerpt:\n{document_snippet}\n\n"
        "Respond with valid JSON only."
    )
    logger.info("LLM verification | model=%s | rule_type=%s", model, rule.get("rule_type"))
    try:
        text = call_openai_chat(system_prompt, user_prompt, model=model)
        text = text.strip()
        idx = text.find('{')
        if idx != -1:
            text = text[idx:]
        parsed = json.loads(text)
        outcome = parsed.get('outcome', 'FAIL')
        confidence = float(parsed.get('confidence', 0.0))
        explanation = parsed.get('explanation', '')
        logger.info(
            "LLM result | model=%s | outcome=%s | confidence=%.2f",
            model,
            outcome,
            confidence,
        )
        return {
            'outcome': outcome,
            'confidence': confidence,
            'explanation': _as_text(explanation),
            'evidence': _as_text(parsed.get('evidence', '')),
            'missing_info': _as_text(parsed.get('missing_info', '')),
            'recommendation': _as_text(parsed.get('recommendation', '')),
            'llm_error': False,
        }
    except Exception as e:
        logger.error("LLM verification failed | model=%s | error=%s", model, e)
        return {
            'outcome': 'FAIL',
            'confidence': 0.0,
            'explanation': f'LLM call failed: {e}',
            'evidence': '',
            'missing_info': 'LLM verification was unavailable.',
            'recommendation': 'Check the API key, selected model, and OpenAI account access.',
            'llm_error': True,
        }
