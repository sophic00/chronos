import io
import pytest
from PIL import Image

from chronos.bot.image_generator import generate_solve_card, generate_summary_card
from chronos.data.database import set_leetcode_target, get_leetcode_target


def _assert_png(img_bytes: bytes, width: int = 1600, height: int = 700):
    assert isinstance(img_bytes, bytes)
    assert img_bytes.startswith(b"\x89PNG")
    with Image.open(io.BytesIO(img_bytes)) as img:
        assert img.size == (width, height)


def test_generate_solve_card():
    # Test leetcode solve card
    leetcode_stats = [
        ("Language", "C++"),
        ("Runtime", "36 ms"),
        ("Memory", "9.0 MB"),
        ("Beats", "92.4%")
    ]
    lc_bytes = generate_solve_card(
        "leetcode", "Two Sum", "Easy", leetcode_stats,
        footer_left="07 Jun 2026, 02:32 PM", footer_right="@mock_lc_username"
    )
    _assert_png(lc_bytes)

    # Test codeforces solve card (rated -> tier-colored badge, tags as chips)
    codeforces_stats = [
        ("Language", "C++23"),
        ("Time", "62 ms"),
        ("Memory", "100 KB"),
        ("Problem", "1899A")
    ]
    cf_bytes = generate_solve_card(
        "codeforces", "Theatre Square", "1300", codeforces_stats,
        tags=["dp", "greedy", "math"],
        footer_left="07 Jun 2026, 02:32 PM", footer_right="@mock_cf_handle"
    )
    _assert_png(cf_bytes)


def test_generate_solve_card_unknown_difficulty():
    """Unrated/unknown difficulty must not break badge rendering (badge hidden)."""
    stats = [("Language", "PyPy 3.10"), ("Time", "62 ms"), ("Memory", "100 KB"), ("Problem", "1A")]
    cf_bytes = generate_solve_card("codeforces", "Unrated Problem", "NA", stats)
    _assert_png(cf_bytes)

    lc_bytes = generate_solve_card("leetcode", "Some Problem", "N/A", stats)
    _assert_png(lc_bytes)


def test_generate_summary_card_no_targets():
    dummy_stats = {
        "leetcode": {"Easy": 3, "Medium": 4, "Hard": 1},
        "codeforces": {"800": 2, "1200": 1, "1500": 2, "1800": 0}
    }

    # 1. Daily
    daily_bytes = generate_summary_card("daily", "June 07, 2026", dummy_stats)
    _assert_png(daily_bytes)

    # 2. Weekly
    weekly_bytes = generate_summary_card("weekly", "Jun 01 - Jun 07, 2026", dummy_stats)
    _assert_png(weekly_bytes)

    # 3. Monthly
    monthly_bytes = generate_summary_card("monthly", "June 2026", dummy_stats)
    _assert_png(monthly_bytes)


def test_generate_summary_card_with_targets_and_extras():
    dummy_stats = {
        "leetcode": {"Easy": 3, "Medium": 4, "Hard": 1},
        "codeforces": {"800": 2, "1200": 1, "1500": 2, "1800": 0}
    }
    targets = {"easy": 2, "medium": 5, "hard": 1}
    extras = {
        "streak": 5,
        "delta": 3,
        "delta_label": "VS YESTERDAY",
        "activity": [("Mo", 1), ("Tu", 0), ("We", 4), ("Th", 2), ("Fr", 0), ("Sa", 3), ("Su", 3)],
        "activity_title": "LAST 7 DAYS",
    }

    # Daily summary with targets (medium not met, easy met, hard met)
    daily_bytes = generate_summary_card("daily", "June 07, 2026", dummy_stats,
                                        targets=targets, extras=extras)
    _assert_png(daily_bytes)

    # Weekly summary with targets
    weekly_bytes = generate_summary_card("weekly", "Jun 01 - Jun 07, 2026", dummy_stats,
                                         targets=targets, extras=extras)
    _assert_png(weekly_bytes)

    # Monthly-style dense activity strip (31 days, no day labels)
    monthly_extras = dict(extras)
    monthly_extras["activity"] = [(str(d), (d * 3) % 5) for d in range(1, 32)]
    monthly_extras["activity_title"] = "JUNE"
    monthly_bytes = generate_summary_card("monthly", "June 2026", dummy_stats,
                                          targets=targets, extras=monthly_extras)
    _assert_png(monthly_bytes)


def test_get_leetcode_target_roundtrip():
    """Targets are stored in the DB but passed to the card purely as a parameter."""
    set_leetcode_target("daily", 2, 5, 1)
    daily_targets = get_leetcode_target("daily")
    assert daily_targets == {"easy": 2, "medium": 5, "hard": 1}
