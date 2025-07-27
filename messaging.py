from typing import Optional

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
