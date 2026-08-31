import re

from telegram.helpers import escape_markdown

_LANGUAGE_NAMES = {
    "cpp": "C++",
    "csharp": "C#",
    "python": "Python",
    "python3": "Python 3",
    "java": "Java",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "ruby": "Ruby",
    "php": "PHP",
    "scala": "Scala",
    "c": "C",
    "dart": "Dart",
    "racket": "Racket",
    "mysql": "MySQL",
    "mssql": "MS SQL Server",
    "postgresql": "PostgreSQL",
    "pandas": "Pandas",
    "bash": "Bash",
}

def prettify_language(language: str | None) -> str:
    """Human-friendly language names: 'cpp' -> 'C++', 'C++23 (GCC 14-64, msys2)' -> 'C++23'."""
    if not language:
        return "N/A"
    base = str(language).split(" (")[0].strip()
    return _LANGUAGE_NAMES.get(base.lower(), base)

def format_bytes(num_bytes) -> str:
    """Formats a byte count as '512 B', '100 KB' or '9.0 MB'."""
    try:
        n = float(num_bytes)
    except (TypeError, ValueError):
        return "N/A"
    if n < 1024:
        return f"{int(n)} B"
    kb = n / 1024
    if kb < 1024:
        return f"{int(round(kb))} KB"
    return f"{kb / 1024:.1f} MB"

def escape_md(text) -> str:
    """Escapes Telegram legacy Markdown special characters in dynamic text.

    Problem titles and handles can contain '_', '*', '[' etc., which would
    otherwise break (or inject) message formatting.
    """
    return escape_markdown(str(text), version=1)


def sanitize_code_block(code: str) -> str:
    """Collapses fence-breaking backtick runs so code renders inside a ``` block."""
    return re.sub(r"`{3,}", "``", code or "")


def cf_rating_bands(cf_stats: dict) -> dict:
    """Aggregates Codeforces solve counts into rating bands.

    Shared by the text summaries and the image cards so the banding cannot
    drift between the two. Returns keys: '800-1000', '1100-1300',
    '1400-1600', '1700+', 'unrated'.
    """
    bands = {"800-1000": 0, "1100-1300": 0, "1400-1600": 0, "1700+": 0, "unrated": 0}
    for rating_str, count in cf_stats.items():
        if str(rating_str).isdigit():
            rating = int(rating_str)
            if 800 <= rating <= 1000:
                bands["800-1000"] += count
            elif 1100 <= rating <= 1300:
                bands["1100-1300"] += count
            elif 1400 <= rating <= 1600:
                bands["1400-1600"] += count
            elif rating >= 1700:
                bands["1700+"] += count
            else:  # Digits but outside any defined band (e.g. 1050)
                bands["unrated"] += count
        else:
            bands["unrated"] += count
    return bands


def format_new_solve_message(
    platform: str,
    problem_name: str,
    problem_url: str,
    difficulty: str | None,
    language: str,
    runtime: str | None,
    memory: str | None,
    code: str | None = None,
    language_ext: str | None = None
) -> str:

    if platform.lower() == "leetcode":
        if difficulty == "Easy":
            difficulty_str = f"{difficulty}"
        elif difficulty == "Medium":
            difficulty_str = f"{difficulty}"
        elif difficulty == "Hard":
            difficulty_str = f"{difficulty}"
        else:
            difficulty_str = f"{difficulty or 'N/A'}"
    else: # Codeforces
        difficulty_str = f"{difficulty or 'N/A'}"

    message = (
        f"👾 *New Solve*\n\n"
        f"⚔️ *Platform:* {escape_md(platform)}\n"
        f"📘 *Problem:* [{escape_md(problem_name)}]({problem_url})\n"
        f"🏷️ *Difficulty:* {escape_md(difficulty_str)}\n"
        f"💻 *Language:* {escape_md(language)}\n"
    )

    if runtime:
        message += f"⚡ *Runtime:* {escape_md(runtime)}\n"
    if memory:
        message += f"🧠 *Memory:* {escape_md(memory)}\n"

    if code and language_ext:
        message += f"\n💡 *Solution:*\n```{language_ext}\n{sanitize_code_block(code)}\n```"
        
    return message 
