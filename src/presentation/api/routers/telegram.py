import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, status
from pydantic import ValidationError

from src.presentation.api.dependencies import BotDep, DispatcherDep, verify_webhook_secret
from src.presentation.api.schemas import ErrorResponse, WebhookAck

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post(
    "/webhook",
    summary="Receive a Telegram update",
    description=(
        "Telegram calls this endpoint for every update. The request is authenticated with the "
        "secret token configured when the webhook was registered. The update is processed "
        "before the response is returned because serverless runtimes may freeze the "
        "instance right after responding."
    ),
    dependencies=[Depends(verify_webhook_secret)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "Invalid webhook secret",
        }
    },
)
async def receive_update(
    payload: Annotated[dict[str, Any], Body()],
    bot: BotDep,
    dispatcher: DispatcherDep,
) -> WebhookAck:
    try:
        await dispatcher.feed_raw_update(bot, payload)
    except ValidationError:
        logger.warning("received an update that does not match the Telegram schema", exc_info=True)
        return WebhookAck(ok=False)
    return WebhookAck(ok=True)
