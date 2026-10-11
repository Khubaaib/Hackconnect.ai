import asyncio
from pathlib import Path
import psycopg
from .config import settings
async def run():
    async with await psycopg.AsyncConnection.connect(settings().database_url) as c:
        await c.execute("SELECT pg_advisory_xact_lock(823040)")
        exists=await (await c.execute("SELECT to_regclass('public.schema_migrations')")).fetchone()
        if exists[0]:print('Migration 001 already applied');return
        sql=(Path(__file__).resolve().parents[2]/'database/001_initial.sql')
        if not sql.exists():sql=Path('/app/database/001_initial.sql')
        # File owns transaction markers; execute within migration connection.
        await c.execute(sql.read_text().replace('BEGIN;','',1).rsplit('COMMIT;',1)[0])
        print('Applied migration 001')
if __name__=='__main__':asyncio.run(run())
