from sim.transcript import Scene, Turn


def test_roundtrip(tmp_path):
    s = Scene(
        scene_id="s1", location="Westfall", channel="GENERAL",
        participants=["Brumdar", "Sylvara"],
        turns=[
            Turn(idx=0, speaker="Brumdar", channel="GENERAL", text="lfg dm anyone?", actions=[]),
            Turn(idx=1, speaker="Sylvara", channel="GENERAL", text="sure inv",
                 actions=[{"type": "invite", "target": "Brumdar"}]),
        ],
    )
    p = tmp_path / "s1.json"
    s.save(p)
    s2 = Scene.load(p)
    assert s2.scene_id == "s1"
    assert len(s2.turns) == 2
    assert s2.turns[1].actions[0]["type"] == "invite"
    assert s2.turns[0].text == "lfg dm anyone?"
