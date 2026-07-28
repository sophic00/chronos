from typing import Optional

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

def prettify_language(language: Optional[str]) -> str:
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

def format_new_solve_message(
    platform: str,
    problem_name: str,
    problem_url: str,
    difficulty: Optional[str],
    language: str,
    runtime: Optional[str],
    memory: Optional[str],
    code: Optional[str] = None,
    language_ext: Optional[str] = None
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
        f"⚔️ *Platform:* {platform}\n"
        f"📘 *Problem:* [{problem_name}]({problem_url})\n"
        f"🏷️ *Difficulty:* {difficulty_str}\n"
        f"💻 *Language:* {language}\n"
    )

    if runtime:
        message += f"⚡ *Runtime:* {runtime}\n"
    if memory:
        message += f"🧠 *Memory:* {memory}\n"

    if code and language_ext:
        message += f"\n💡 *Solution:*\n```{language_ext}\n{code}\n```"
        
    return message 
