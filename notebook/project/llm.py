import json
import os
import re
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = os.environ.get("MODEL_NAME", "Qwen/Qwen2.5-1.5B-Instruct")
_cache = {}
LOAD_COUNT = 0


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(model_name=MODEL_NAME):
    global LOAD_COUNT
    if model_name not in _cache:
        start = time.time()
        device = get_device()
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForCausalLM.from_pretrained(model_name, dtype="auto").to(device)
        _cache[model_name] = (tokenizer, model)
        LOAD_COUNT += 1
        print(f"[llm] loaded {model_name} on {device} in {time.time() - start:.1f}s")
    return _cache[model_name]


def chat(messages, max_new_tokens=300, model_name=MODEL_NAME):
    tokenizer, model = load_model(model_name)
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs, max_new_tokens=max_new_tokens, do_sample=False,
            temperature=None, top_p=None, top_k=None,
        )
    new_tokens = output[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()


def extract_json(text):
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates += [text[i:] for i, ch in enumerate(text) if ch == "{"]
    decoder = json.JSONDecoder()
    for candidate in candidates:
        try:
            obj, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    raise ValueError(f"No JSON object found in model output: {text[:200]!r}")


if __name__ == "__main__":
    start = time.time()
    print(chat([{"role": "user", "content": "Say hello in 5 words"}], max_new_tokens=30))
    print(f"[llm] total time {time.time() - start:.1f}s")
