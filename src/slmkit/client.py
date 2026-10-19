"""One OpenAI-compatible client for every target: teacher API, base and tuned model on vLLM.

vLLM serves the untrained base model as `base` and the LoRA adapter as `model`
(serve/start_vllm.sh), so base vs tuned is just a different model name on the same server.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI

from slmkit.settings import die, env, output_schema, system_prompt


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
            extra: dict = {"chat_template_kwargs": {"enable_thinking": False}}
            if self.guided_json:
                # vLLM structured outputs: decoding is constrained to the schema.
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
        return Completion(
            text=resp.choices[0].message.content or "",
            latency_s=latency,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
