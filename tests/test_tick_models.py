from models import TickRequest


def test_tick_request_accepts_grounded_state_fields():
    req = TickRequest(bot_name="Esterini", location="Elwynn Forest",
                      subzone="Goldshire", activity="in_combat", target="Kobold Vermin")
    assert req.subzone == "Goldshire"
    assert req.activity == "in_combat"
    assert req.target == "Kobold Vermin"


def test_tick_request_grounded_fields_default_none():
    req = TickRequest(bot_name="Esterini")
    assert req.subzone is None and req.activity is None and req.target is None
