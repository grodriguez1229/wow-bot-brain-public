import prompts


def test_both_prompts_have_identity_placeholder():
    assert "{identity_section}" in prompts.CHAT_PROMPT
    assert "{identity_section}" in prompts.TICK_PROMPT


def test_chat_prompt_allows_real_world_topics():
    # person-open framing: modern/real-world topics are explicitly permitted
    assert "wider world" in prompts.CHAT_LIFE_RULE_OPEN


def test_game_world_still_locked_vanilla():
    assert "no expansions" in prompts.CHAT_PROMPT
    assert "no expansions" in prompts.TICK_PROMPT


def test_chat_prompt_formats_with_identity_section():
    # all placeholders fillable, including the new one
    out = prompts.CHAT_PROMPT.format(
        who="a tired dwarf", typing_style="terse", mood="chill", name="Bot",
        level=16, race="Dwarf", class_name="Rogue", faction="Alliance",
        current_goal="hit 20", motivation_line="", self_section="",
        identity_section="WHO YOU'VE BECOME:\n- cynical about pugs",
        context_section="", memory_section="", nearby_section="", action_rules="", life_rule="",
        examples_section="", moments_section="")
    assert "cynical about pugs" in out
