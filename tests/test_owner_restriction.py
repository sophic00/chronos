from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update
from telegram.ext import ContextTypes

from chronos.bot.handlers import restrict_to_owner
from chronos.config import settings


@pytest.mark.asyncio
async def test_restrict_to_owner_no_config(mocker):
    """If OWNER_USER_ID is not set, allow command to execute."""
    settings.OWNER_USER_ID = None
    
    mock_func = AsyncMock()
    decorated = restrict_to_owner(mock_func)
    
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await decorated(update, context)
    mock_func.assert_called_once_with(update, context)

@pytest.mark.asyncio
async def test_restrict_to_owner_authorized(mocker):
    """If OWNER_USER_ID is set and matches user ID, allow command to execute."""
    settings.OWNER_USER_ID = 99999
    
    mock_func = AsyncMock()
    decorated = restrict_to_owner(mock_func)
    
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 99999
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await decorated(update, context)
    mock_func.assert_called_once_with(update, context)

@pytest.mark.asyncio
async def test_restrict_to_owner_unauthorized(mocker):
    """If OWNER_USER_ID is set and user ID does not match, block command and reply with error."""
    settings.OWNER_USER_ID = 99999
    
    mock_func = AsyncMock()
    decorated = restrict_to_owner(mock_func)
    
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock()
    update.effective_user.id = 11111  # Unauthorized
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    await decorated(update, context)
    
    mock_func.assert_not_called()
    update.message.reply_text.assert_called_once_with("❌ Unauthorized: Only the bot owner can access this command.")
