from typing import Any

import asyncpg

from .config import DATABASE_URL

pool: asyncpg.Pool | None = None


async def connect() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)


async def close() -> None:
    if pool:
        await pool.close()


async def execute(query: str, *args: Any) -> str:
    assert pool is not None
    async with pool.acquire() as connection:
        return await connection.execute(query, *args)


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    assert pool is not None
    async with pool.acquire() as connection:
        return await connection.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    assert pool is not None
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, *args)

