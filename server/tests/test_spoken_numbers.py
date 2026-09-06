from server.services.spoken_numbers import expand_spoken_numbers


def test_expands_rupee_amount():
    assert "five thousand" in expand_spoken_numbers("That comes to 5000 rupees.")


def test_expands_indian_mobile_digit_by_digit():
    out = expand_spoken_numbers("Call 9876543210 now.")
    assert "nine eight seven six five four three two one zero" in out
    assert "9876543210" not in out


def test_leaves_plot_two_alone():
    assert expand_spoken_numbers("plot 2 is ready") == "plot 2 is ready"


def test_expands_otp_near_label():
    assert "four zero one two" in expand_spoken_numbers("OTP is 4012")


def test_expands_clock():
    assert "ten AM" in expand_spoken_numbers("Come at 10:00 AM")
