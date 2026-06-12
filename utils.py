import subprocess, json, os

def call_claude(prompt: str, system: str = "") -> str:
    """
    Call claude CLI in headless bare mode.
    Returns the plain-text result string.
    Raises RuntimeError on non-zero exit.
    """
    # --bare skips keychain auth and needs ANTHROPIC_API_KEY (the CI path).
    # Locally, without the key, fall back to normal -p mode + keychain login.
    cmd = ["claude"]
    if os.environ.get("ANTHROPIC_API_KEY"):
        cmd.append("--bare")
    cmd += ["-p", prompt, "--output-format", "json"]
    if system:
        cmd += ["--append-system-prompt", system]

    # CLAUDECODE must be cleared so the CLI can run from inside a Claude Code session
    env = {**os.environ, "CLAUDECODE": ""}

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        timeout=300
    )

    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed:\n{result.stderr}")

    payload = json.loads(result.stdout)
    if payload.get("is_error"):
        raise RuntimeError(f"claude CLI error: {payload.get('result')}")
    return payload["result"]   # plain text response
