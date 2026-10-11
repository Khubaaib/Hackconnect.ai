from starlette.responses import JSONResponse
class BodyLimitMiddleware:
    """Limit chunked bodies too; content-length alone is not sufficient."""
    def __init__(self,app,limit=6*1024*1024):self.app=app;self.limit=limit
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        if scope['method'] in ('POST','PUT','PATCH'):
            chunks=[];size=0
            while True:
                msg=await receive()
                if msg['type']=='http.disconnect':return
                size+=len(msg.get('body',b''))
                if size>self.limit:
                    return await JSONResponse({'detail':'Request too large'},status_code=413)(scope,receive,send)
                chunks.append(msg)
                if not msg.get('more_body',False):break
            async def replay():
                if chunks:return chunks.pop(0)
                return await receive()
            return await self.app(scope,replay,send)
        await self.app(scope,receive,send)
