from server.services.saas.script_variables import merge_variables, variables_from_text


def test_variables_extracted_from_tags():
    greeting = "Hi {{caller_name}}, welcome to {{business_name}}."
    script = "Ask about {{budget_inr}} and {{site_visit_date}}."
    keys = [v["key"] for v in variables_from_text(greeting, script)]
    assert "caller_name" in keys
    assert "business_name" in keys
    assert "budget_inr" in keys


def test_merge_variables_prefers_llm_metadata():
    greeting = "Hello {{caller_name}}"
    script = "Confirm {{callback_phone}}"
    merged = merge_variables(
        [{"key": "caller_name", "label": "Name", "description": "d", "source": "caller"}],
        greeting,
        script,
    )
    by_key = {v["key"]: v for v in merged}
    assert by_key["caller_name"]["source"] == "caller"
    assert "callback_phone" in by_key
