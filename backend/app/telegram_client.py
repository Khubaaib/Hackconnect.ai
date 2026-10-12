"""Bounded, read-only synchronization of one configured Telegram channel."""
import asyncio
import logging
import re
import binascii
import struct
from .config import settings
from . import db
from psycopg.types.json import Jsonb

log = logging.getLogger('hackconnect.telegram')
_sync_lock = asyncio.Lock()
_event_terms = re.compile(r'\b(hack[ -]?athons?|hackfest|hack[ -]?challenges?|ideathons?|codeathons?|coding\s+(?:contest|competition|challenge)|project\s+competitions?)\b', re.I)

def configured(s=None):
    s = s or settings()
    return bool(s.telegram_api_id and s.telegram_api_hash and s.telegram_session_string
                and re.fullmatch(r'-100\d+', s.telegram_channel_id))

def parse_session(raw):
    """Accept a copied dotenv value without exposing reusable account credentials."""
    from telethon.sessions import StringSession
    value=raw.strip().removeprefix('TELEGRAM_SESSION_STRING=').strip()
    if len(value)>1 and value[0]==value[-1] and value[0] in ('\"', "'"):
        value=value[1:-1]
    value=re.sub(r'\s+','',value)
    if len(value) not in (353,369) or not value.startswith('1'):
        raise RuntimeError('invalid_session_format')
    try:
        session=StringSession(value)
        if not session.auth_key:
            raise RuntimeError('invalid_session_format')
        return session
    except (ValueError,struct.error,binascii.Error):
        raise RuntimeError('invalid_session_format') from None

def announcement(message, channel_id, username=None):
    """Preserve original text; never infer dates, prizes, or registration requirements."""
    body = (getattr(message, 'message', None) or '')[:40000]
    has_media = bool(getattr(message, 'photo', None) or getattr(message, 'document', None))
    if not body.strip() and not has_media:
        return None  # Ignore service messages and empty entries.
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    title = (lines[0][:180] if lines else 'Announcement attachment')
    named=re.search(r'(?:Event Name|Hackathon Name)\s*:\s*(.*?)(?:[🔹🛠🏆🔗📍🌐]|\n|$)',body,re.I)
    if named and named.group(1).strip():
        title=named.group(1).strip()[:180]
    if username and re.fullmatch(r'[A-Za-z0-9_]+', username):
        source = f'https://t.me/{username}/{message.id}'
    else:
        if not re.fullmatch(r'-100\d+', channel_id):
            raise ValueError('Invalid channel ID')
        source = f'https://t.me/c/{channel_id[4:]}/{message.id}'
    # Poster-only messages remain visible as attachments requiring source inspection.
    relevant = bool(_event_terms.search(body)) or has_media
    return dict(message_id=message.id, title=title, body=body, source_url=source,
                posted_at=message.date, edited_at=getattr(message, 'edit_date', None),
                has_media=has_media, relevant=relevant)

async def store_message(c, channel_id, message, username=None):
    item = announcement(message, channel_id, username)
    if item is None:
        return
    await c.execute('''INSERT INTO telegram_announcements
        (channel_id,message_id,title,body,source_url,posted_at,edited_at,has_media,relevant)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT(channel_id,message_id) DO UPDATE SET
        title=excluded.title,body=excluded.body,source_url=excluded.source_url,
        edited_at=excluded.edited_at,has_media=excluded.has_media,
        relevant=excluded.relevant,deleted=false,synced_at=now()''',
        (channel_id, item['message_id'], item['title'], item['body'], item['source_url'],
         item['posted_at'], item['edited_at'], item['has_media'], item['relevant']))
    await queue_for_review(c,channel_id,item)

async def queue_for_review(c,channel_id,item):
    source=await db.one(c,"SELECT id FROM hackathon_sources WHERE reference=%s AND authorized=true",('telegram:'+channel_id,))
    if not source:
        return
    reference=str(item['message_id'])
    previous=await db.one(c,'SELECT id,payload FROM ingestion_events WHERE source_id=%s AND reference=%s FOR UPDATE',(source['id'],reference))
    if not item['relevant'] and not previous:
        return
    payload={'text':item['body'],'title':item['title'],'source_url':item['source_url'],
             'has_media':item['has_media'],'edited_at':item['edited_at'].isoformat() if item['edited_at'] else None}
    if previous and previous['payload']==payload:
        return  # Repeated polling must preserve an administrator's review.
    await c.execute("""INSERT INTO ingestion_events(source_id,reference,payload) VALUES(%s,%s,%s)
        ON CONFLICT(source_id,reference) DO UPDATE SET payload=excluded.payload,status='pending',updated_at=now()""",
        (source['id'],reference,Jsonb(payload)))
    if previous:
        await c.execute("""UPDATE hackathons SET verification_status='pending',updated_at=now(),
            quality_flags=CASE WHEN 'source_edited'=ANY(quality_flags) THEN quality_flags ELSE array_append(quality_flags,'source_edited') END
            WHERE source_id=%s AND source_reference=%s""",(source['id'],reference))

async def remove_announcement(c,channel_id,message_id):
    await c.execute('UPDATE telegram_announcements SET deleted=true,synced_at=now() WHERE channel_id=%s AND message_id=%s',(channel_id,message_id))
    source=await db.one(c,'SELECT id FROM hackathon_sources WHERE reference=%s',('telegram:'+channel_id,))
    if source:
        await c.execute("UPDATE ingestion_events SET status='source_deleted',updated_at=now() WHERE source_id=%s AND reference=%s",(source['id'],str(message_id)))
        await c.execute("UPDATE hackathons SET cancelled=true,verification_status='needs_correction',updated_at=now() WHERE source_id=%s AND source_reference=%s",(source['id'],str(message_id)))

async def _sync(s):
    from telethon import TelegramClient, utils
    client = TelegramClient(parse_session(s.telegram_session_string), s.telegram_api_id,
                            s.telegram_api_hash.strip(), receive_updates=False,
                            request_retries=2, connection_retries=2, flood_sleep_threshold=0)
    async with db.connection() as c:
        lock = await db.one(c, 'SELECT pg_try_advisory_xact_lock(3919421009) AS acquired')
        if not lock['acquired']:
            return {'status': 'busy'}
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError('authorization_required')
            entity = None
            # StringSession has no entity cache. Resolve only the selected dialog;
            # no other dialog's messages are fetched or stored.
            async for dialog in client.iter_dialogs(limit=500):
                if str(utils.get_peer_id(dialog.entity)) == s.telegram_channel_id:
                    entity = dialog.entity
                    break
            if entity is None:
                raise RuntimeError('channel_access_required')
            await c.execute("""INSERT INTO hackathon_sources(name,kind,reference,authorized)
                VALUES(%s,'telegram',%s,true) ON CONFLICT(reference) DO NOTHING""",(entity.title,'telegram:'+s.telegram_channel_id))
            previous = await db.one(c, '''SELECT greatest(
                coalesce((SELECT max(message_id) FROM telegram_announcements WHERE channel_id=%s),0),
                coalesce((SELECT newest_message_id FROM telegram_sync_state WHERE channel_id=%s),0)) AS newest''', (s.telegram_channel_id,s.telegram_channel_id))
            newest = previous['newest'] or 0
            latest_seen = newest
            count = 0
            # First import: most recent 200 posts. Later runs: oldest unread first,
            # so bursts over 200 posts are drained without silently skipping gaps.
            async for message in client.iter_messages(entity, limit=200, min_id=newest, reverse=bool(newest)):
                await store_message(c, s.telegram_channel_id, message, getattr(entity, 'username', None))
                count += 1
                latest_seen = max(latest_seen, message.id)
            recent = await db.all_rows(c, 'SELECT message_id FROM telegram_announcements WHERE channel_id=%s ORDER BY message_id DESC LIMIT 200', (s.telegram_channel_id,))
            ids = [r['message_id'] for r in recent]
            if ids:
                # Reconcile edits and removals in the recent window, not just new posts.
                messages = await client.get_messages(entity, ids=ids)
                for expected_id, message in zip(ids, messages):
                    if message is None or not getattr(message, 'date', None):
                        await remove_announcement(c,s.telegram_channel_id,expected_id)
                    else:
                        await store_message(c, s.telegram_channel_id, message, getattr(entity, 'username', None))
            await c.execute('''INSERT INTO telegram_sync_state(channel_id,channel_title,last_success_at,newest_message_id)
                VALUES(%s,%s,now(),%s) ON CONFLICT(channel_id) DO UPDATE SET
                channel_title=excluded.channel_title,last_success_at=now(),
                newest_message_id=greatest(telegram_sync_state.newest_message_id,excluded.newest_message_id),last_error=NULL''',
                (s.telegram_channel_id, entity.title, latest_seen))
            return {'status': 'synced', 'new_posts_checked': count}
        finally:
            await client.disconnect()

async def sync_once():
    s = settings()
    if not configured(s):
        return {'status': 'not_configured'}
    if _sync_lock.locked():
        return {'status': 'busy'}
    async with _sync_lock:
        try:
            return await asyncio.wait_for(_sync(s), timeout=90)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never emit RPC payloads, credentials, session strings, or raw posts.
            code = 'sync_failed'
            if isinstance(exc, RuntimeError) and str(exc) in ('authorization_required', 'channel_access_required', 'invalid_session_format'):
                code = str(exc)
            log.warning('telegram_sync_failed type=%s', type(exc).__name__)
            try:
                async with db.connection() as c:
                    await c.execute('''INSERT INTO telegram_sync_state(channel_id,last_error)
                        VALUES(%s,%s) ON CONFLICT(channel_id) DO UPDATE SET last_error=excluded.last_error''', (s.telegram_channel_id, code))
            except Exception:
                log.warning('telegram_sync_status_unavailable')
            return {'status': code}

async def poll():
    while True:
        await sync_once()
        await asyncio.sleep(max(60, settings().telegram_sync_interval_seconds))
