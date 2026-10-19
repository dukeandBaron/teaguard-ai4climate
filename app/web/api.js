/** The only browser transport boundary; POST requests are never auto-retried. */
export function createApiClient({fetchImpl = globalThis.fetch, timeoutMs = 10000} = {}) {
  return async function call(path, payload) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const options = {signal: controller.signal};
      if (payload !== undefined) {
        Object.assign(options, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      }
      const response = await fetchImpl(path, options);
      let data;
      try {
        data = await response.json();
      } catch {
        throw Object.assign(new Error('本机服务返回了无法识别的结果，请确认服务已启动。'), {code: 'INVALID_RESPONSE'});
      }
      if (!response.ok) {
        throw Object.assign(new Error(data.error || '本机请求未完成。'), {code: data.code, requestId: data.request_id});
      }
      return data;
    } catch (error) {
      if (error.name === 'AbortError') {
        throw Object.assign(new Error('本机请求超时；原记录保留。请检查服务后手动重试。'), {code: 'REQUEST_TIMEOUT'});
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  };
}
