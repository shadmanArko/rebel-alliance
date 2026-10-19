"""One OpenAI-compatible client for every target: teacher API, base and tuned model on vLLM.

vLLM serves the untrained base model as `base` and the LoRA adapter as `model`
(serve/start_vllm.sh), so base vs tuned is just a different model name on the same server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI

from slmkit.settings import (
    die,
    env,
    max_completion_tokens,
    output_schema,
    student_thinking,
    system_prompt,
)

# Qwen3.5 vendor sampling for thinking mode; Distil evaluates reasoning students with it.
THINKING_SAMPLING = {"temperature": 1.0, "top_p": 0.95}
THINKING_EXTRA = {"top_k": 20}


@dataclass
class Target:
    name: str
    base_url: str
    api_key: str
    model: str
    is_student: bool  # students get the training-time chat settings and guided JSON


def resolve_target(name: str) -> Target:
    if name == "teacher":
        base_url, model = env("TEACHER_BASE_URL"), env("TEACHER_MODEL")
        if not (base_url and model):
            die("teacher endpoint not configured: set TEACHER_BASE_URL and TEACHER_MODEL in .env")
        return Target(name, base_url, env("TEACHER_API_KEY", "EMPTY"), model, False)
    if name in ("base", "tuned"):
        base_url = env("SERVE_BASE_URL")
        if not base_url:
            die("SERVE_BASE_URL is empty: start the vLLM pod first (serve/README.md)")
        model = "base" if name == "base" else "model"
        return Target(name, base_url, env("SERVE_API_KEY", "EMPTY"), model, True)
    die(f"unknown target {name!r}; use teacher, base or tuned")


@dataclass
class Completion:
    text: str
    reasoning: str
    latency_s: float
    prompt_tokens: int
    completion_tokens: int


class ModelClient:
    def __init__(self, target: Target, guided_json: bool = True, timeout: float = 120.0):
        self.target = target
        self.guided_json = guided_json
        self.client = OpenAI(base_url=target.base_url, api_key=target.api_key, timeout=timeout)

    def complete(self, user_content: str) -> Completion:
        kwargs: dict = {}
        if self.target.is_student:
            thinking = student_thinking()
            extra: dict = {"chat_template_kwargs": {"enable_thinking": thinking}}
            kwargs["max_tokens"] = max_completion_tokens()
            if thinking:
                kwargs.update(THINKING_SAMPLING)
                extra.update(THINKING_EXTRA)
            if self.guided_json:
                # vLLM structured outputs: the answer is constrained to the schema. With the
                # reasoning parser on (serve/start_vllm.sh), the thinking block is left free.
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "output", "schema": output_schema()},
                }
            kwargs["extra_body"] = extra
        messages = [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_content},
        ]
        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.target.model, messages=messages, **kwargs
        )
        latency = time.perf_counter() - start
        usage = resp.usage
        message = resp.choices[0].message
        # vLLM's reasoning parser returns the thinking as reasoning_content (newer: reasoning)
        reasoning = getattr(message, "reasoning_content", None) or getattr(message, "reasoning", None)
        return Completion(
            text=message.content or "",
            reasoning=reasoning or "",
            latency_s=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
