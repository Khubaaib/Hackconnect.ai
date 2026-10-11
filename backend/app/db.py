from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from .config import settings
pool: AsyncConnectionPool | None = None
async def open_pool():
    global pool
    if settings().database_url:
        pool=AsyncConnectionPool(settings().database_url,min_size=1,max_size=10,open=False,kwargs={'row_factory':dict_row,'prepare_threshold':None})
        await pool.open(); await pool.wait(timeout=10)
async def close_pool():
    if pool: await pool.close()
def connection():
    if pool is None:
        from fastapi import HTTPException
        raise HTTPException(503,'Database is not configured')
    return pool.connection()
async def all_rows(c,sql,args=()): return await (await c.execute(sql,args)).fetchall()
async def one(c,sql,args=()): return await (await c.execute(sql,args)).fetchone()
