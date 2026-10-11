from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def test_health():assert client.get('/health').json()['status']=='ok'
def test_ready_without_db_is_not_success():assert client.get('/ready').status_code==503
def test_profile_requires_auth():assert client.get('/api/v1/me').status_code==401
def test_team_messages_require_auth():assert client.get('/api/v1/teams/00000000-0000-0000-0000-000000000001/messages').status_code==401
def test_admin_requires_auth():assert client.get('/api/v1/admin/overview').status_code==401
def test_telegram_secret_is_required():assert client.post('/api/v1/integrations/telegram',json={}).status_code==403
def test_job_secret_is_required():assert client.post('/api/v1/jobs/checks').status_code==403
def test_request_size_rejected():assert client.post('/api/v1/jobs/checks',headers={'Content-Length':str(8*1024*1024)}).status_code==413
def test_cors_rejects_other_origin():
    r=client.options('/health',headers={'Origin':'https://evil.example','Access-Control-Request-Method':'GET'})
    assert r.status_code==400
