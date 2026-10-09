import json
import logging
import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika

from .config import RABBITMQ_URL, SERVICE_NAME
from .telemetry import event_log, increment
from .web import correlation_id_context

logger = logging.getLogger("parcelpulse.events")
exchange_name = "parcelpulse.events"


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    metadata: dict[str, Any] = {"producer": SERVICE_NAME, "correlation_id": correlation_id_context.get()}
    carrier: dict[str, str] = {}
    try:
        from opentelemetry import propagate
        propagate.inject(carrier)
    except ImportError:
        pass
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel = await connection.channel()
        exchange = await channel.declare_exchange(exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
        message = aio_pika.Message(
            json.dumps({"type": event_type, "payload": payload, "metadata": {**metadata, "trace_context": carrier}}).encode(),
            content_type="application/json",
        )
        await exchange.publish(message, routing_key=event_type)
    increment("parcelplus.events.published", attributes={"event": event_type})
    event_log("event_published", event_type=event_type, correlation_id=metadata["correlation_id"])


async def consume(service_name: str, event_types: list[str], handler: Callable[[str, dict[str, Any]], Awaitable[None]]) -> None:
    # Compose can report RabbitMQ healthy a moment before the AMQP port is
    # ready. Keep consumers alive and reconnect rather than losing the
    # service's event loop on the first connection-refused error.
    while True:
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(exchange_name, aio_pika.ExchangeType.TOPIC, durable=True)
                queue = await channel.declare_queue(f"{service_name}.events", durable=True)
                for event_type in event_types:
                    await queue.bind(exchange, routing_key=event_type)
                async with queue.iterator() as messages:
                    async for message in messages:
                        async with message.process():
                            data = json.loads(message.body)
                            metadata = data.get("metadata", {})
                            payload = data["payload"]
                            payload.setdefault("correlation_id", metadata.get("correlation_id", "-"))
                            correlation_token = correlation_id_context.set(payload["correlation_id"])
                            try:
                                from opentelemetry import context, propagate
                                parent = propagate.extract(metadata.get("trace_context", {}))
                                attach_token = context.attach(parent)
                            except ImportError:
                                attach_token = None
                                context = None
                            try:
                                await handler(data["type"], payload)
                                increment("parcelplus.events.consumed", attributes={"event": data["type"]})
                                event_log("event_consumed", consumer_service=service_name, event_type=data["type"], correlation_id=payload["correlation_id"])
                            finally:
                                if attach_token is not None and context is not None:
                                    context.detach(attach_token)
                                correlation_id_context.reset(correlation_token)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("event_consumer_reconnecting service=%s error=%s", service_name, exc)
            await asyncio.sleep(2)
