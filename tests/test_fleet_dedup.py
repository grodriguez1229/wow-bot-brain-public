import election


def setup_function():
    election.reset_state()


def test_exact_repeat_is_duplicate():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    assert election.is_duplicate_line("Anyone up for Deadmines?", now=101.0) is True


def test_distinct_line_is_not_duplicate():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    assert election.is_duplicate_line("this kobold nearly had me, close one", now=101.0) is False


def test_high_overlap_is_duplicate():
    election.note_fleet_line("lf healer for deadmines run", now=100.0)
    # same request, trivially reworded -> high token overlap
    assert election.is_duplicate_line("lf a healer for deadmines run pls", now=101.0) is True


def test_expired_lines_do_not_count():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    # beyond the window -> no longer compared
    assert election.is_duplicate_line("anyone up for Deadmines?", now=100.0 + 10_000) is False


def test_empty_text_is_never_duplicate():
    election.note_fleet_line("", now=100.0)
    assert election.is_duplicate_line("", now=101.0) is False


def test_reset_state_clears_fleet_window():
    election.note_fleet_line("anyone up for Deadmines?", now=100.0)
    election.reset_state()
    assert election.is_duplicate_line("anyone up for Deadmines?", now=101.0) is False
