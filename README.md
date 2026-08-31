# Chronos

Telegram bot to monitor and log solved problems on LeetCode and Codeforces. It formats solved problems as clean image cards and broadcasts them to a configured Telegram channel. Additionally, the bot supports private chat commands for querying personal statistics and configuring daily, weekly, or monthly coding targets.

---

## Project Structure

```text
.
├── .dockerignore
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml
├── assets/                  # Static preview assets + vendored fonts/logos
│   ├── fonts/
│   ├── solve_codeforces.png
│   ├── solve_leetcode.png
│   └── summary_daily.png
├── chronos/
│   ├── bot/
│   │   ├── handlers.py      # Commands, summaries, image orchestration
│   │   ├── image_generator.py
│   │   └── messaging.py
│   ├── config/
│   │   ├── constants.py
│   │   └── settings.py
│   ├── data/
│   │   ├── database.py      # SQLAlchemy ORM service + wrappers
│   │   ├── models.py
│   │   └── state_manager.py
│   ├── integrations/
│   │   ├── codeforces.py
│   │   └── leetcode.py
│   └── main.py
├── Dockerfile
├── deploy.sh
├── pyproject.toml
└── tests/
    ├── conftest.py
    ├── test_database.py
    ├── test_image_generator.py
    ├── test_integrations.py
    ├── test_owner_restriction.py
    ├── test_settings.py
    └── test_stats_handlers.py
```

The `data/` directory is runtime-only (SQLite database and any downloaded
asset fallbacks) and is excluded from the Docker build context.

---

## Development

```bash
uv sync                 # install runtime + dev dependencies from uv.lock
uv run pytest -q        # run the test suite
uv run ruff check .     # lint
```

---

## Image Cards Preview

When `SEND_AS_IMAGE=True` is enabled in the configuration, the bot generates and posts image cards to the Telegram channel instead of standard text messages.

### Solve Cards

|             LeetCode Solve Card              |              Codeforces Solve Card               |
| :------------------------------------------: | :----------------------------------------------: |
| ![LeetCode Solve](assets/solve_leetcode.png) | ![Codeforces Solve](assets/solve_codeforces.png) |

### Summary Cards

| Daily / Weekly / Monthly Progress Summary |
| :---------------------------------------: |
| ![Summary Card](assets/summary_daily.png) |

---

## Available Bot Commands

All commands must be executed in a private chat with the bot.

| Command    | Usage                          | Description                                                                                 |
| :--------- | :----------------------------- | :------------------------------------------------------------------------------------------ |
| `/help`    | `/help`                        | Lists all available bot commands and their usages.                                          |
| `/ping`    | `/ping`                        | Verifies bot latency and returns connection response.                                       |
| `/stats`   | `/stats`                       | Retrieves coding statistics and target progress for the current day.                        |
| `/wstats`  | `/wstats`                      | Retrieves coding statistics and target progress for the current week (Monday–Sunday).       |
| `/mstats`  | `/mstats`                      | Retrieves coding statistics and target progress for the current month.                      |
| `/pstats`  | `/pstats`                      | Retrieves coding statistics for the previous day.                                           |
| `/pwstats` | `/pwstats`                     | Retrieves coding statistics for the previous week.                                          |
| `/dset`    | `/dset <easy> <medium> <hard>` | Configures daily LeetCode targets (e.g., `/dset 2 1 0` for 2 Easy, 1 Medium, 0 Hard).       |
| `/wset`    | `/wset <easy> <medium> <hard>` | Configures weekly LeetCode targets (e.g., `/wset 10 5 1` for 10 Easy, 5 Medium, 1 Hard).    |
| `/mset`    | `/mset <easy> <medium> <hard>` | Configures monthly LeetCode targets (e.g., `/mset 40 20 5` for 40 Easy, 20 Medium, 5 Hard). |

---

## Configuration

Refer to the `.env.example` file for details on setting up scraper credentials and configuring bot features, including `SEND_AS_IMAGE`.
