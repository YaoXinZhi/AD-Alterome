"""Restricted, opt-in Codex CLI transport for one structured LLM response.

This bridge uses the CLI's existing login. It never reads authentication files,
copies credentials, or makes the website a general-purpose agent interface.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


DISABLED_FEATURES = (
    "shell_tool", "unified_exec", "apps", "plugins", "browser_use",
    "browser_use_external", "computer_use", "in_app_browser", "multi_agent",
    "multi_agent_v2", "memories", "hooks", "plugin_hooks", "image_generation",
    "code_mode", "code_mode_only", "goals", "workspace_dependencies",
    "skill_mcp_dependency_install", "skill_search", "view_image", "sleep_tool",
    "in_app_chat", "in_app_local_automation", "in_app_updates", "remote_plugin",
    "standalone_web_search", "send_message_to_user_async", "code_mode_host",
)


class CodexCompletionError(RuntimeError):
    def __init__(self, message, trace):
        super().__init__(message)
        self.trace = trace


def restricted_environment():
    # Authentication remains managed by Codex. No Django/API secrets are passed.
    allowed = ("HOME", "PATH", "CODEX_HOME", "TMPDIR", "LANG", "LC_ALL",
               "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
               "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
    return {key: os.environ[key] for key in allowed if key in os.environ}


def codex_json_completion(system_prompt, user_prompt, schema, *, model,
                          reasoning_effort, timeout, executable="codex"):
    resolved_executable = shutil.which(executable)
    if not resolved_executable:
        raise CodexCompletionError("Codex CLI is not available", {})
    if reasoning_effort not in {"low", "medium", "high", "xhigh"}:
        raise CodexCompletionError("Unsupported Codex reasoning setting", {})

    started = time.perf_counter()
    trace = {"transport": "codex-cli", "requested_model": model,
             "reasoning_effort": reasoning_effort, "tool_calls": [],
             "jsonl": "", "stderr": "", "events": []}
    with tempfile.TemporaryDirectory(prefix="adalterome-llm-") as workdir:
        schema_path = Path(workdir) / "response-schema.json"
        instructions_path = Path(workdir) / "instructions.txt"
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        instructions = (system_prompt + "\nUse only the supplied input. Do not invoke tools, "
                        "skills, file access, or external searches. Return the JSON response only.")
        instructions_path.write_text(instructions, encoding="utf-8")
        trace["instructions"] = instructions
        trace["output_schema"] = schema
        command = [resolved_executable, "exec", "--ignore-user-config",
                   "--ignore-rules", "--ephemeral", "--skip-git-repo-check",
                   "--json", "--color", "never", "--sandbox", "read-only",
                   "--model", model, "--output-schema", str(schema_path),
                   "-C", workdir,
                   "-c", 'model_reasoning_effort=' + json.dumps(reasoning_effort),
                   "-c", 'model_instructions_file=' + json.dumps(str(instructions_path)),
                   "-c", 'model_provider="openai-http"',
                   "-c", 'model_providers.openai-http.name="OpenAI HTTP"',
                   "-c", "model_providers.openai-http.requires_openai_auth=true",
                   "-c", "model_providers.openai-http.supports_websockets=false",
                   "-c", 'web_search="disabled"',
                   "-c", 'approval_policy="never"',
                   "-c", "project_doc_max_bytes=0",
                   "--enable", "skip_host_skill_discovery",
                   "-c", "mcp_servers={}",
                   "-c", 'shell_environment_policy.inherit="none"']
        for feature in DISABLED_FEATURES:
            command.extend(["--disable", feature])
        command.append("-")
        # The real command and input are retained for the server-side audit only.
        trace["command"] = command
        trace["stdin"] = user_prompt
        try:
            result = subprocess.run(
                command, input=user_prompt, text=True, capture_output=True,
                cwd=workdir, env=restricted_environment(), timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            trace["jsonl"] = _as_text(exc.stdout)
            trace["stderr"] = _as_text(exc.stderr)
            trace["duration_seconds"] = time.perf_counter() - started
            raise CodexCompletionError("Codex request timed out", trace) from exc
        trace.update({"jsonl": result.stdout, "stderr": result.stderr,
                      "returncode": result.returncode,
                      "duration_seconds": time.perf_counter() - started})
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict):
                trace["events"].append(event)

        # Reject any unexpected tool-bearing event even if the CLI exits cleanly.
        messages, completions = [], []
        for event in trace["events"]:
            item = event.get("item") or {}
            item_type = item.get("type")
            if item_type and item_type not in {"agent_message", "reasoning", "error"}:
                trace["tool_calls"].append(item)
            if event.get("type") == "item.completed" and item_type == "agent_message":
                messages.append(item.get("text", ""))
            if event.get("type") == "turn.completed":
                completions.append(event)
        # Recoverable transport errors can precede a valid final response. Keep
        # them in the audit, but require the completed turn and successful exit.
        trace["transport_errors"] = [
            event for event in trace["events"]
            if event.get("type") == "error" or (event.get("item") or {}).get("type") == "error"
        ]
        if any(event.get("type") == "turn.failed" for event in trace["events"]):
            raise CodexCompletionError("Codex reported a failed response", trace)
        if trace["tool_calls"]:
            raise CodexCompletionError("Unexpected tool activity in a summary call", trace)
        if result.returncode or not completions or not messages:
            raise CodexCompletionError("Codex request did not complete", trace)
        text = messages[-1]
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise CodexCompletionError("Codex did not return valid JSON", trace) from exc
        if not isinstance(payload, dict):
            raise CodexCompletionError("Codex response must be a JSON object", trace)
        trace["output_text"] = text
        trace["usage"] = completions[-1].get("usage") or {}
        # exec JSONL does not necessarily disclose a returned model identifier.
        # Keep this unknown rather than relabeling the requested model as observed.
        trace["response_model"] = next(
            (event["model"] for event in trace["events"] if isinstance(event.get("model"), str)),
            None,
        )
        return text, trace


def _as_text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
