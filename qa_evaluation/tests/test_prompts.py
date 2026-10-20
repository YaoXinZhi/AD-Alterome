"""Network-free checks for prompt boundaries and request construction."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("prompts", ROOT / "qa_evaluation/prompt_templates.py")
templates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(templates)


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.questions = json.loads((ROOT / "qa_evaluation/questions.json").read_text())
        self.question = next(q for q in self.questions if q["id"] == "G4")

    def test_no_kb_receives_no_sources_or_tools(self):
        request = templates.initial_request(self.question, "no_kb")
        self.assertEqual(len(request["messages"]), 2)
        self.assertNotIn("tools", request)
        self.assertEqual(request["tool_choice"], "none")
        self.assertEqual(request["messages"][1]["content"], templates.prompt("common").replace("{QUESTION}", self.question["en"]))

    def test_mcp_passes_source_sentences_without_overview_or_scores(self):
        evidence = [{"RefID": 1, "Sentence": "A source sentence.", "PMID": "12345678", "EvidenceScore": 99}]
        request = templates.initial_request(self.question, "mcp", records=evidence)
        text = request["messages"][1]["content"].split("Retrieved evidence records:\n")[1]
        payload = json.loads(text)
        self.assertEqual(payload[0]["Sentence"], evidence[0]["Sentence"])
        self.assertEqual(set(payload[0]), set(templates.CITATION_FIELDS))
        self.assertNotIn("tools", request)

    def test_skills_enforces_query_then_selected_only_packet(self):
        request = templates.initial_request(self.question, "skills", skill_text="Frozen instructions.\n")
        definition = request["tools"][0]["function"]
        self.assertEqual(definition["parameters"]["properties"]["gene"]["enum"], ["PINK1"])
        call = {"id": "call_example", "type": "function", "function": {
            "name": definition["name"], "arguments": '{"gene":"PINK1"}'}}
        final = templates.skills_final_request(request, {"content": None, "tool_calls": [call]}, "Selected evidence.")
        self.assertNotIn("tools", final)
        self.assertEqual(final["tool_choice"], "none")
        self.assertEqual(json.loads(final["messages"][-1]["content"]), {"knowledge_packet": "Selected evidence."})
        self.assertEqual(len(request["messages"]), 2)
        call["function"]["arguments"] = '{"gene":"APP"}'
        with self.assertRaises(ValueError):
            templates.skills_final_request(request, {"tool_calls": [call]}, "irrelevant")

    def test_all_conditions_preserve_shared_limits_and_question(self):
        for question in self.questions:
            for condition in ["no_kb", "mcp", "skills"]:
                request = templates.initial_request(question, condition, records=[], skill_text="Instructions")
                self.assertIn(question["en"], request["messages"][1]["content"])
                self.assertEqual(request["max_tokens"], 2000)
                self.assertEqual(request["temperature"], 0)
                self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})


if __name__ == "__main__":
    unittest.main()
