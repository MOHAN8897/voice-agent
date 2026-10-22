from server.call.hangup_judge import caller_declines_more_help, caller_withdrew_callback


def test_no_maam_is_not_callback_withdrawal():
    assert not caller_withdrew_callback("No, ma'am.")
    assert caller_declines_more_help("No, ma'am.")


def test_explicit_dont_call_is_withdrawal():
    assert caller_withdrew_callback("No, you don't have to call me.")
    assert not caller_declines_more_help("No, you don't have to call me.")
