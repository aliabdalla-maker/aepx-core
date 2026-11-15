"""ADLC Validate stage: static checks of agent output (nothing is executed)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.validation import report, validate_answer


def test_checks_python_and_json_blocks_and_names_files():
    text = ("Here:\n```python src/app.py\ndef ok():\n    return 1\n```\n"
            "```python src/bad.py\ndef broken(:\n```\n"
            "```json\n{\"a\": 1}\n```\n```json config.json\n{bad}\n```\n```bash\nrm -rf /\n```\n")
    r = validate_answer(text)
    assert (r["checked"], r["passed"], r["skipped"]) == (4, 2, 1)
    assert r["problems"][0].startswith("src/bad.py: Python syntax error on line 1")
    assert r["problems"][1].startswith("config.json: Invalid JSON")
    assert "2/4 code blocks passed" in report(text)


def test_no_code_means_no_report():
    assert report("Just a plan, no code.") == ""
    assert validate_answer("```\nplain\n```")["skipped"] == 1
