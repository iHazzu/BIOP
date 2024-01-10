# -*- coding: utf-8 -*-
import aiomysql
from typing import Optional, Tuple, List, Any


class DataBase:
    def __init__(self, max_conections: int) -> None:
        self.max_conections = max_conections
        self.pool: Optional[aiomysql.Pool] = None

    async def connect(self, dsn: str) -> None:
        params = dict(kwarg.split(":") for kwarg in dsn.split())
        self.pool = await aiomysql.create_pool(maxsize=self.max_conections, autocommit=True, **params)

    def close(self) -> None:
        self.pool.terminate()

    async def set(self, querry: str, *valores: Any) -> None:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(querry, valores)

    async def get(self, querry: str, *valores: Any) -> List[Tuple]:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(querry, valores)
                return await cur.fetchall()

    async def set_count(self, querry: str, *valores: Any) -> int:
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(querry, valores)
                return cur.rowcount