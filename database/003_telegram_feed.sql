-- Original announcements from the operator-selected channel. No Telegram credentials.
BEGIN;
CREATE TABLE IF NOT EXISTS public.telegram_announcements (
    channel_id text NOT NULL,
    message_id bigint NOT NULL,
    title text NOT NULL,
    body text NOT NULL,
    source_url text NOT NULL,
    posted_at timestamptz NOT NULL,
    edited_at timestamptz,
    has_media boolean NOT NULL DEFAULT false,
    relevant boolean NOT NULL DEFAULT false,
    deleted boolean NOT NULL DEFAULT false,
    synced_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, message_id)
);
CREATE INDEX IF NOT EXISTS telegram_feed_recent ON public.telegram_announcements(channel_id, posted_at DESC);
CREATE TABLE IF NOT EXISTS public.telegram_sync_state (
    channel_id text PRIMARY KEY,
    channel_title text NOT NULL DEFAULT '',
    last_success_at timestamptz,
    newest_message_id bigint NOT NULL DEFAULT 0,
    last_error text
);
ALTER TABLE public.telegram_announcements ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telegram_sync_state ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.telegram_announcements, public.telegram_sync_state FROM anon, authenticated;
COMMIT;
