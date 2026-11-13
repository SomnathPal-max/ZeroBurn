"""Python equivalent of check_gateway.sh for cross-platform execution."""
from __future__ import annotations

import os
import json
import httpx
from pathlib import Path

def load_env() -> dict[str, str]:
    env_file = Path(".env")
    env = dict(os.environ)
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("\"'")
    return env

def main() -> int:
    env = load_env()
    base_url = env.get("BIFROST_URL", "http://localhost:8080/v1").rstrip("/")
    if base_url.endswith("/v1"):
        endpoint = f"{base_url}/chat/completions"
    else:
        endpoint = f"{base_url}/v1/chat/completions"

    vk_standard = env.get("BIFROST_VK_STANDARD", "sk-bf-standard")
    vk_confidential = env.get("BIFROST_VK_CONFIDENTIAL", "sk-bf-confidential")
    cloud_model = env.get("CLOUD_MODEL", "openai/gpt-4o-mini")
    local_model = env.get("LOCAL_MODEL", "ollama/llama3.2:latest")

    print(f"Testing Gateway at {endpoint}")
    print(f"Standard Virtual Key: {vk_standard}")
    print(f"Confidential Virtual Key: {vk_confidential}")

    passed = True
    with httpx.Client(timeout=10.0) as client:
        # Check (a): Standard + cloud
        print("Checking (a) standard key + cloud model: ", end="", flush=True)
        try:
            res_a = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {vk_standard}", "x-bf-vk": vk_standard},
                json={"model": cloud_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if res_a.status_code == 200:
                print("PASS")
            else:
                print(f"FAIL (HTTP {res_a.status_code}: {res_a.text})")
                passed = False
        except Exception as e:
            print(f"FAIL (Connection error: {e})")
            passed = False

        # Check (b): Confidential + Ollama
        print("Checking (b) confidential key + Ollama model: ", end="", flush=True)
        try:
            res_b = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {vk_confidential}", "x-bf-vk": vk_confidential},
                json={"model": local_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if res_b.status_code == 200:
                print("PASS")
            else:
                print(f"FAIL (HTTP {res_b.status_code}: {res_b.text})")
                passed = False
        except Exception as e:
            print(f"FAIL (Connection error: {e})")
            passed = False

        # Check (c): Confidential + Cloud (MUST BE REJECTED)
        print("Checking (c) confidential key + cloud model rejected: ", end="", flush=True)
        try:
            res_c = client.post(
                endpoint,
                headers={"Authorization": f"Bearer {vk_confidential}", "x-bf-vk": vk_confidential},
                json={"model": cloud_model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5},
            )
            if res_c.status_code in (400, 403, 422):
                print(f"PASS (Rejected with HTTP {res_c.status_code})")
            else:
                print(f"FAIL (Expected rejection 400/403/422, got HTTP {res_c.status_code}: {res_c.text})")
                passed = False
        except Exception as e:
            print(f"FAIL (Connection error: {e})")
            passed = False

    return 0 if passed else 1

if __name__ == "__main__":
    raise SystemExit(main())
