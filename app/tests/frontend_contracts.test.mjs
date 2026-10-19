import assert from 'node:assert/strict';
import test from 'node:test';

const apiModule = await import('../web/api.js').catch(() => null);

test('API errors retain the recovery code and diagnostic request ID', async () => {
  assert.ok(apiModule, 'Dedicated API boundary is missing');
  const call = apiModule.createApiClient({fetchImpl: async () => ({ok:false,json:async()=>({error:'找不到记录',code:'RECORD_NOT_FOUND',request_id:'test123'})})});
  await assert.rejects(call('/api/analyze', {}), error => error.code === 'RECORD_NOT_FOUND' && error.requestId === 'test123');
});

test('A timed-out POST is surfaced and never silently retried', async () => {
  assert.ok(apiModule, 'Dedicated API boundary is missing');
  let attempts = 0;
  const call = apiModule.createApiClient({timeoutMs:10,fetchImpl:async(_path,options)=>{
    attempts++;
    return new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(Object.assign(new Error('aborted'),{name:'AbortError'}))));
  }});
  await assert.rejects(call('/api/feedback', {}), error => error.code === 'REQUEST_TIMEOUT');
  assert.equal(attempts, 1);
});

test('Non-JSON responses become a clear local-service error', async () => {
  assert.ok(apiModule, 'Dedicated API boundary is missing');
  const call=apiModule.createApiClient({fetchImpl:async()=>({ok:true,json:async()=>{throw new SyntaxError('html instead of JSON');}})});
  await assert.rejects(call('/api/bootstrap'), error=>error.code==='INVALID_RESPONSE');
});
