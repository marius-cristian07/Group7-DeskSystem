"""Check daily time windows, including those crossing midnight."""

DAY = 24 * 60 * 60


def to_seconds(value):
    return (value.hour * 3600 + value.minute * 60
            + value.second + value.microsecond / 1_000_000)


def schedules_overlap(start_a, end_a, start_b, end_b):
    a_start, a_end = to_seconds(start_a), to_seconds(end_a)
    b_start, b_end = to_seconds(start_b), to_seconds(end_b)

    if a_start == a_end or b_start == b_end:
        raise ValueError("Start and end must differ")
    if a_end < a_start:
        a_end += DAY
    if b_end < b_start:
        b_end += DAY

    # Daily schedules repeat; an overnight interval may overlap a neighbouring day.
    return any(
        a_start < b_end + shift and b_start + shift < a_end
        for shift in (-DAY, 0, DAY)
    )
