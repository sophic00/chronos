from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from chronos.bot.handlers import (
    help_handler,
    monthly_stats_handler,
    past_day_stats_handler,
    past_week_stats_handler,
    stats_handler,
    weekly_stats_handler,
)
from chronos.config import settings


@pytest.mark.asyncio
async def test_stats_handler_send_as_image(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_daily_stats_from_db", return_value={
        "leetcode": {"Easy": 1},
        "codeforces": {}
    })
    mocker.patch("chronos.bot.handlers.generate_summary_card", return_value=b"fake_daily_image_bytes")
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await stats_handler(update, context)
    
    update.message.reply_photo.assert_called_once()
    update.message.reply_text.assert_not_called()
    
    args, kwargs = update.message.reply_photo.call_args
    assert kwargs["photo"].read() == b"fake_daily_image_bytes"
    assert "Grand Total Solved Today" in kwargs["caption"]

@pytest.mark.asyncio
async def test_stats_handler_fallback_to_text(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", False)
    mocker.patch("chronos.bot.handlers.get_daily_stats_from_db", return_value={
        "leetcode": {"Easy": 1},
        "codeforces": {}
    })
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await stats_handler(update, context)
    
    update.message.reply_photo.assert_not_called()
    update.message.reply_text.assert_called_once()
    assert "Grand Total Solved Today" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_stats_handler_zero_solves_falls_back_to_text(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_daily_stats_from_db", return_value={})
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await stats_handler(update, context)
    
    update.message.reply_photo.assert_not_called()
    update.message.reply_text.assert_called_once()
    assert "You haven't solved any new problems" in update.message.reply_text.call_args[0][0]

@pytest.mark.asyncio
async def test_weekly_stats_handler_send_as_image(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_weekly_stats_from_db", return_value={
        "leetcode": {"Medium": 2},
        "codeforces": {}
    })
    mocker.patch("chronos.bot.handlers.generate_summary_card", return_value=b"fake_weekly_image_bytes")
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await weekly_stats_handler(update, context)
    
    update.message.reply_photo.assert_called_once()
    update.message.reply_text.assert_not_called()
    
    args, kwargs = update.message.reply_photo.call_args
    assert kwargs["photo"].read() == b"fake_weekly_image_bytes"
    assert "Grand Total Solved This Week" in kwargs["caption"]

@pytest.mark.asyncio
async def test_monthly_stats_handler_send_as_image(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_monthly_stats_from_db", return_value={
        "leetcode": {"Hard": 1},
        "codeforces": {}
    })
    mocker.patch("chronos.bot.handlers.generate_summary_card", return_value=b"fake_monthly_image_bytes")
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await monthly_stats_handler(update, context)
    
    update.message.reply_photo.assert_called_once()
    update.message.reply_text.assert_not_called()
    
    args, kwargs = update.message.reply_photo.call_args
    assert kwargs["photo"].read() == b"fake_monthly_image_bytes"
    assert "Grand Total Solved This Month" in kwargs["caption"]

@pytest.mark.asyncio
async def test_past_day_stats_handler_send_as_image(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_past_day_stats_from_db", return_value={
        "leetcode": {"Easy": 2},
        "codeforces": {}
    })
    mocker.patch("chronos.bot.handlers.generate_summary_card", return_value=b"fake_yesterday_image_bytes")
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await past_day_stats_handler(update, context)
    
    update.message.reply_photo.assert_called_once()
    update.message.reply_text.assert_not_called()
    
    args, kwargs = update.message.reply_photo.call_args
    assert kwargs["photo"].read() == b"fake_yesterday_image_bytes"
    assert "Grand Total Solved Yesterday" in kwargs["caption"]

@pytest.mark.asyncio
async def test_past_week_stats_handler_send_as_image(mocker):
    mocker.patch.object(settings, "SEND_AS_IMAGE", True)
    mocker.patch("chronos.bot.handlers.get_past_week_stats_from_db", return_value={
        "leetcode": {"Easy": 5},
        "codeforces": {}
    })
    mocker.patch("chronos.bot.handlers.generate_summary_card", return_value=b"fake_last_week_image_bytes")
    
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_photo = AsyncMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await past_week_stats_handler(update, context)
    
    update.message.reply_photo.assert_called_once()
    update.message.reply_text.assert_not_called()
    
    args, kwargs = update.message.reply_photo.call_args
    assert kwargs["photo"].read() == b"fake_last_week_image_bytes"
    assert "Grand Total Solved Last Week" in kwargs["caption"]


@pytest.mark.asyncio
async def test_help_handler(mocker):
    update = MagicMock(spec=Update)
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await help_handler(update, context)
    
    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    help_text = args[0]
    assert "Chronos Bot Help" in help_text
    assert "/stats" in help_text
    assert "/wstats" in help_text
    assert "/mstats" in help_text
    assert "/pstats" in help_text
    assert "/pwstats" in help_text
    assert "/dset" in help_text
    assert "/wset" in help_text
    assert "/mset" in help_text
    assert "/ping" in help_text
    assert "/help" in help_text
