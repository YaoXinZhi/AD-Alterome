"""Portable rendering of the recorded evaluation prompts; makes no API calls."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CITATION_FIELDS = ("RefID", "Gene", "TermName", "Hypothesis", "PMID", "Journal", "Year", "Sentence")


def prompt(name):
    # Published files have one conventional trailing newline; recorded messages do not.
    return (HERE / "prompts" / f"{name}.txt").read_text(encoding="utf-8").removesuffix("\n")


def initial_request(question, condition, *, records=None, skill_text=None):
    if condition not in {"no_kb", "mcp", "skills"}:
        raise ValueError("Unknown condition")
    system = prompt(condition)
    user = prompt("common").replace("{QUESTION}", question["en"])
    if condition == "mcp":
        if records is None:
            raise ValueError("Supply MCP evidence records; an empty list is allowed")
        evidence = [{key: trace.get(key) for key in CITATION_FIELDS} for trace in records]
        user += "\n\nRetrieved evidence records:\n" + json.dumps(evidence, ensure_ascii=False)
    elif condition == "skills":
        if skill_text is None:
            raise ValueError("Supply the pinned external knowledge-synthesis SKILL.md")
        system += "\n\nProvided Skill instructions:\n" + skill_text
    settings = json.loads((HERE / "generation-settings.json").read_text(encoding="utf-8"))
    request = {
        "model": settings["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens_per_model_call"],
        "extra_body": {"thinking": settings["thinking"]},
    }
    if condition == "skills":
        kind = question["kind"]
        if kind not in {"gene", "term", "hypothesis"}:
            raise ValueError("Only the prespecified single-axis routes were evaluated")
        name = "build_adalterome_knowledge_synthesis"
        request["tools"] = [{"type": "function", "function": {
            "name": name,
            "description": f"Execute the provided revised native single-{kind} Skill builder against the frozen AD-Alterome database; return its selected, sentence-audited knowledge packet. Candidate limit 500 and organized limit 18. No external searches or source-link access.",
            "parameters": {"type": "object", "properties": {
                kind: {"type": "string", "enum": [question["query"]],
                       "description": f"The prespecified {kind} label requested in the question."}},
                "required": [kind], "additionalProperties": False},
        }}]
        request["tool_choice"] = {"type": "function", "function": {"name": name}}
    else:
        request["tool_choice"] = "none"
    return request


def skills_final_request(initial, assistant_message, knowledge_packet):
    """Append the actual validated builder call and selected-only packet, without new instructions."""
    import copy
    request = copy.deepcopy(initial)
    calls = assistant_message.get("tool_calls") or []
    if len(calls) != 1:
        raise ValueError("Exactly one builder call is required")
    definition = request["tools"][0]["function"]
    call = calls[0]
    arguments = json.loads(call["function"]["arguments"])
    properties = definition["parameters"]["properties"]
    if call["function"]["name"] != definition["name"] or set(arguments) != set(properties):
        raise ValueError("Builder call is outside the prescribed route")
    for key, value in arguments.items():
        if not isinstance(value, str) or value.strip().casefold() != properties[key]["enum"][0].casefold():
            raise ValueError("Builder argument differs from the prespecified query")
    request["messages"].extend([
        {"role": "assistant", "content": assistant_message.get("content"), "tool_calls": calls},
        {"role": "tool", "tool_call_id": call["id"],
         "content": json.dumps({"knowledge_packet": knowledge_packet}, ensure_ascii=False)},
    ])
    request.pop("tools")  # The recorded final call exposes no additional tools.
    request["tool_choice"] = "none"
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("condition", choices=["no_kb", "mcp", "skills"])
    parser.add_argument("question_id")
    parser.add_argument("--evidence", type=Path, help="MCP evidence list or context containing evidence_traces")
    parser.add_argument("--skill-file", type=Path, help="Pinned external knowledge-synthesis SKILL.md")
    args = parser.parse_args()
    questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    question = next((q for q in questions if q["id"] == args.question_id), None)
    if question is None:
        parser.error("Unknown question ID")
    records = json.loads(args.evidence.read_text(encoding="utf-8")) if args.evidence else None
    if isinstance(records, dict):
        records = records["evidence_traces"]
    skill = args.skill_file.read_text(encoding="utf-8") if args.skill_file else None
    try:
        request = initial_request(question, args.condition, records=records, skill_text=skill)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(request, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
