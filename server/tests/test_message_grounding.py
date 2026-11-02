from types import SimpleNamespace

from server.services.message_grounding import facts, unsupported

BRAIN = "Sunrise Dental, 14 MG Road. Open Monday to Saturday, 10 AM to 8 PM. Cleaning costs Rs 1,499."


def _ctx(**extra):
    return SimpleNamespace(**{"compiled_brain_text": BRAIN, "business_answers": [], "turn_action_results": [], **extra})


def test_times_and_numbers_are_read_however_they_are_written():
    assert facts("Open 10 AM to 8 p.m.") == {"time 10:00", "time 20:00"}
    assert facts("10:00-20:00, booked for 2026-11-08T15:00") >= {"time ~10:00", "time 20:00", "time 15:00"}
    assert facts("Cleaning is Rs 1,499 at 14 MG Road") == {"number 1499", "number 14"}


def test_invented_opening_hours_are_refused():
    sms = {"to": "+919876543210", "body": "Sunrise Dental timings: Mon-Sat 9 AM to 7 PM."}
    assert unsupported("TWILIO_SMS_SEND_MESSAGE", sms, _ctx(), ["text me the timings"]) == ["time 09:00", "time 19:00"]


def test_facts_from_instructions_the_call_and_the_caller_pass():
    sms = {"to": "+919876543210", "body": "We are at 14 MG Road, open 10 AM to 8 PM. Cleaning is Rs 1499."}
    assert unsupported("TWILIO_SMS_SEND_MESSAGE", sms, _ctx(), []) == []
    booking = [{"action": "GOOGLECALENDAR_CREATE_EVENT", "result": {"time": "2026-11-07T11:00:00+05:30"}}]
    mail = {"to": "a@b.com", "subject": "Booked for 7 Nov", "body": "See you at 11 AM on 07 November 2026, order 5531."}
    assert unsupported("GMAIL_SEND_EMAIL", mail, _ctx(turn_action_results=booking), ["my ticket is 5531"]) == []


def test_only_messages_to_the_caller_are_checked():
    assert unsupported("SLACK_SEND_MESSAGE", {"message": "Call back at 9 PM"}, _ctx(), []) == []
    assert unsupported("TWILIO_SMS_SEND_MESSAGE", {"body": "9 AM"}, None, []) == []


def test_a_time_range_with_one_am_pm_is_read_once_and_either_half_of_the_day():
    booking = [{"action": "GOOGLECALENDAR_CREATE_EVENT", "result": {"time": "2026-11-08T15:00:00+05:30", "end": "15:30"}}]
    mail = {"to": "a@b.com", "subject": "Confirmed", "body": "Your slot is 3:00 - 3:30 PM on 8 November."}
    assert unsupported("GMAIL_SEND_EMAIL", mail, _ctx(turn_action_results=booking), []) == []
    assert unsupported("GMAIL_SEND_EMAIL", {"to": "a@b.com", "body": "Come at 4:15 please"}, _ctx(), []) == ["time ~04:15"]
