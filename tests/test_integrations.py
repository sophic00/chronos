import pytest
from unittest.mock import AsyncMock, MagicMock
from chronos.integrations.leetcode import check_leetcode_submissions
from chronos.integrations.codeforces import check_codeforces_submissions

@pytest.mark.asyncio
async def test_leetcode_spam_prevention(mocker):
    """Verify that uninitialized LeetCode state (timestamp=0) initializes baseline without spamming."""
    # Mock state functions
    mocker.patch("chronos.integrations.leetcode.get_last_leetcode_timestamp", return_value=0)
    save_mock = mocker.patch("chronos.integrations.leetcode.save_last_leetcode_timestamp")
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "recentAcSubmissionList": [
                {
                    "id": "1000",
                    "title": "Two Sum",
                    "titleSlug": "two-sum",
                    "timestamp": "1620000000",
                    "lang": "python3"
                }
            ]
        }
    }
    
    mocker.patch("httpx.AsyncClient.post", return_value=mock_response)
    
    # Mock context and bot
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    
    # Run checker
    await check_leetcode_submissions(context)
    
    # Assertions
    save_mock.assert_called_once_with(1620000000)
    context.bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_codeforces_spam_prevention(mocker):
    """Verify that uninitialized Codeforces state (ID=0) initializes baseline without spamming."""
    # Mock state functions
    mocker.patch("chronos.integrations.codeforces.get_last_submission_id", return_value=0)
    save_mock = mocker.patch("chronos.integrations.codeforces.save_last_submission_id")
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "OK",
        "result": [
            {
                "id": 500,
                "contestId": 1,
                "index": "A",
                "verdict": "OK",
                "creationTimeSeconds": 1620000000,
                "programmingLanguage": "GNU C++17",
                "timeConsumedMillis": 15,
                "memoryConsumedBytes": 1024,
                "problem": {
                    "contestId": 1,
                    "index": "A",
                    "name": "Theatre Square",
                    "rating": 1000
                }
            }
        ]
    }
    
    mocker.patch("httpx.AsyncClient.get", return_value=mock_response)
    
    # Mock context and bot
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    
    # Run checker
    await check_codeforces_submissions(context)
    
    # Assertions
    save_mock.assert_called_once_with(500)
    context.bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_leetcode_duplicate_solve_skips_api_calls(mocker):
    """Verify that an already solved problem skips calling LeetCode GraphQL APIs."""
    mocker.patch("chronos.integrations.leetcode.get_last_leetcode_timestamp", return_value=1620000000 - 10)
    mocker.patch("chronos.integrations.leetcode.is_problem_solved", return_value=True)
    save_mock = mocker.patch("chronos.integrations.leetcode.save_last_leetcode_timestamp")
    difficulty_mock = mocker.patch("chronos.integrations.leetcode.get_leetcode_problem_difficulty")
    
    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "data": {
            "recentAcSubmissionList": [
                {
                    "id": "1000",
                    "title": "Two Sum",
                    "titleSlug": "two-sum",
                    "timestamp": "1620000000",
                    "lang": "python3"
                }
            ]
        }
    }
    mocker.patch("httpx.AsyncClient.post", return_value=mock_response)
    
    # Mock context and bot
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    
    # Run checker
    await check_leetcode_submissions(context)
    
    # Assertions
    save_mock.assert_called_once_with(1620000000)
    difficulty_mock.assert_not_called()
    context.bot.send_message.assert_not_called()

