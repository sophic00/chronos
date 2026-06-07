import pytest
from chronos.bot.image_generator import generate_solve_card, generate_summary_card
from chronos.data.database import set_leetcode_target, get_leetcode_target

def test_generate_solve_card():
    # Test leetcode solve card
    leetcode_stats = [
        ("Rank", "120,453"),
        ("Solved", "450/3100"),
        ("Easy", "200"),
        ("Medium", "200"),
        ("Hard", "50")
    ]
    lc_bytes = generate_solve_card("leetcode", "Two Sum", "Easy", leetcode_stats)
    assert isinstance(lc_bytes, bytes)
    assert lc_bytes.startswith(b"\x89PNG")

    # Test codeforces solve card
    codeforces_stats = [
        ("Rating", "1420"),
        ("Max Rating", "1500"),
        ("Solved", "120"),
        ("Rank", "Specialist")
    ]
    cf_bytes = generate_solve_card("codeforces", "Theatre Square", "1000", codeforces_stats)
    assert isinstance(cf_bytes, bytes)
    assert cf_bytes.startswith(b"\x89PNG")

def test_generate_summary_card_no_targets():
    dummy_stats = {
        "leetcode": {"Easy": 3, "Medium": 4, "Hard": 1},
        "codeforces": {"800": 2, "1200": 1, "1500": 2, "1800": 0}
    }
    
    # 1. Daily
    daily_bytes = generate_summary_card("daily", "June 07, 2026", dummy_stats)
    assert isinstance(daily_bytes, bytes)
    assert daily_bytes.startswith(b"\x89PNG")

    # 2. Weekly
    weekly_bytes = generate_summary_card("weekly", "Jun 01 - Jun 07, 2026", dummy_stats)
    assert isinstance(weekly_bytes, bytes)
    assert weekly_bytes.startswith(b"\x89PNG")

    # 3. Monthly
    monthly_bytes = generate_summary_card("monthly", "June 2026", dummy_stats)
    assert isinstance(monthly_bytes, bytes)
    assert monthly_bytes.startswith(b"\x89PNG")

def test_generate_summary_card_with_targets():
    dummy_stats = {
        "leetcode": {"Easy": 3, "Medium": 4, "Hard": 1},
        "codeforces": {"800": 2, "1200": 1, "1500": 2, "1800": 0}
    }
    
    # Set targets in database
    set_leetcode_target("daily", 2, 5, 1)
    set_leetcode_target("weekly", 10, 15, 5)
    
    # Verify daily targets are set
    daily_targets = get_leetcode_target("daily")
    assert daily_targets == {"easy": 2, "medium": 5, "hard": 1}
    
    # Daily summary with targets (medium not met, easy met, hard met)
    daily_bytes = generate_summary_card("daily", "June 07, 2026", dummy_stats)
    assert isinstance(daily_bytes, bytes)
    assert daily_bytes.startswith(b"\x89PNG")

    # Weekly summary with targets
    weekly_bytes = generate_summary_card("weekly", "Jun 01 - Jun 07, 2026", dummy_stats)
    assert isinstance(weekly_bytes, bytes)
    assert weekly_bytes.startswith(b"\x89PNG")
