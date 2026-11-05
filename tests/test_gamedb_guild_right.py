import gamedb


class _Cur:
    def __init__(self, row): self._row = row
    def execute(self, *a, **k): pass
    def fetchone(self): return self._row
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _Conn:
    def __init__(self, row): self._row = row
    def cursor(self): return _Cur(self._row)
    def close(self): pass


def test_has_invite_right_when_bit_set(monkeypatch):
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn((4,)))
    assert gamedb.lookup_guild_invite_right("Officerbot") is True


def test_no_invite_right_when_bit_clear(monkeypatch):
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn((1,)))
    assert gamedb.lookup_guild_invite_right("Memberbot") is False


def test_no_right_when_not_guilded(monkeypatch):
    monkeypatch.setattr(gamedb.pymysql, "connect", lambda **k: _Conn(None))
    assert gamedb.lookup_guild_invite_right("Solobot") is False
