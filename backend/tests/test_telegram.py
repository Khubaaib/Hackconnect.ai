from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from app import telegram_client as tg
from app.main import app

CHANNEL='-1003919421009'
def message(body='',media=False,message_id=12):
    return SimpleNamespace(id=message_id,message=body,date=datetime.now(timezone.utc),
                           edit_date=None,photo=object() if media else None,document=None)

def test_original_text_and_post_link_are_preserved():
    body='CMRCET Hackathon\nRegister through the attached notice. Deadline not provided.'
    item=tg.announcement(message(body),CHANNEL)
    assert item['body']==body
    assert item['source_url']=='https://t.me/c/3919421009/12'
    assert item['relevant'] is True
    assert not any(k in item for k in ('deadline','registration_url','prizes'))

def test_non_event_chat_is_not_classified_as_hackathon():
    assert tg.announcement(message('Good morning everyone'),CHANNEL)['relevant'] is False

def test_captioned_and_captionless_posters_are_retained():
    for body in ('','Registration details in the attached poster'):
        item=tg.announcement(message(body,media=True),CHANNEL)
        assert item['has_media'] and item['relevant']

def test_empty_service_updates_are_ignored():
    assert tg.announcement(message(),CHANNEL) is None

def test_source_url_cannot_inject_external_host():
    item=tg.announcement(message('Hackathon'),CHANNEL,'evil.example/path')
    assert item['source_url'].startswith('https://t.me/c/')

def test_sync_requires_all_credentials_and_a_marked_channel_id():
    s=SimpleNamespace(telegram_api_id=1,telegram_api_hash='test',telegram_session_string='test',telegram_channel_id=CHANNEL)
    assert tg.configured(s)
    s.telegram_session_string=''
    assert not tg.configured(s)
    s.telegram_session_string='test';s.telegram_channel_id='some-other-channel'
    assert not tg.configured(s)

@pytest.mark.asyncio
async def test_upsert_is_scoped_to_selected_channel():
    c=SimpleNamespace(execute=AsyncMock())
    await tg.store_message(c,CHANNEL,message('Hackathon',message_id=33))
    sql,args=c.execute.call_args.args
    assert 'ON CONFLICT(channel_id,message_id)' in sql
    assert args[:2]==(CHANNEL,33)

@pytest.mark.asyncio
async def test_errors_never_expose_session_or_raw_exception(monkeypatch):
    monkeypatch.setattr(tg,'configured',lambda s=None:True)
    async def fail(s):raise ValueError('private-session-value')
    monkeypatch.setattr(tg,'_sync',fail)
    # Error-status persistence may fail too; the public result remains safe.
    assert await tg.sync_once()=={'status':'sync_failed'}

@pytest.mark.asyncio
async def test_concurrent_sync_is_skipped(monkeypatch):
    monkeypatch.setattr(tg,'configured',lambda s=None:True)
    async with tg._sync_lock:
        assert await tg.sync_once()=={'status':'busy'}

def test_feed_and_manual_sync_require_authentication():
    client=TestClient(app)
    assert client.get('/api/v1/telegram/announcements').status_code==401
    assert client.post('/api/v1/admin/telegram/sync').status_code==401
