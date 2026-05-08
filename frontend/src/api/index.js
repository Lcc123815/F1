import axios from 'axios'

// 开发期：通过 Vite 代理 /api -> http://localhost:8000
const api = axios.create({
  baseURL: '',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use(
  config => {
    const token = localStorage.getItem('token')
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
  },
  error => Promise.reject(error)
)

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
    }
    return Promise.reject(err)
  }
)

export default {
  // ============== 业务接口 ==============
  getStocks(params) { return api.get('/stocks', { params }) },
  getStockKline(code, kType = 8, limit = 60, region) { return api.get('/api/itick/kline', { params: { code, kType, limit, region } }) },
  factorList() { return api.get('/api/factor/list') },
  factorAnalyze(payload) { return api.post('/api/factor/analyze', payload, { timeout: 300000 }) },
  factorCacheStatus(codes, limit = 150) { return api.get('/api/factor/cache_status', { params: { codes, limit } }) },
  mlStatus() { return api.get('/api/ml/status') },
  mlTrain(payload) { return api.post('/api/ml/train', payload, { timeout: 300000 }) },
  mlPredict(payload) { return api.post('/api/ml/predict', payload, { timeout: 120000 }) },
  getBacktest() { return api.get('/backtest/latest') },
  runBacktest(payload) { return api.post('/api/backtest/run', payload) },
  listStrategies() { return api.get('/api/backtest/strategies') },

  // ============== 认证接口 ==============
  login(data) { return api.post('/api/login', data) },
  register(data) { return api.post('/api/register', data) },
  forgotPassword(data) { return api.post('/api/forgot-password', data) },

  // ============== 分类股票池（核心/普通/禁买）==============
  poolList(params) { return api.get('/api/pool', { params }) },
  poolAdd(data) { return api.post('/api/pool', data) },
  poolUpdateCategory(id, category) { return api.patch(`/api/pool/${id}/category`, { category }) },
  poolUpdateNote(id, note) { return api.patch(`/api/pool/${id}/note`, { note }) },
  poolRemove(id) { return api.delete(`/api/pool/${id}`) },

  // ============== iTick 行情代理（A股/港股/美股）==============
  itickQuote(code, region) { return api.get('/api/itick/quote', { params: { code, region } }) },
  itickQuotes(codes, region) { return api.get('/api/itick/quotes', { params: { codes: codes.join(','), region } }) },
  itickKline(code, kType = 6, limit = 60, region) { return api.get('/api/itick/kline', { params: { code, kType, limit, region } }) },
  itickInfo(code, region) { return api.get('/api/itick/info', { params: { code, region } }) },

  // ============== 舆情情感（HF 小模型 + 词典回退）==============
  sentimentStatus() { return api.get('/api/sentiment/status') },
  sentimentNews(code, days = 7, limit = 30) { return api.get('/api/sentiment/news', { params: { code, days, limit }, timeout: 60000 }) },
  sentimentBatch(codes, days = 7, limit = 20) { return api.post('/api/sentiment/batch', { codes, days, limit }, { timeout: 120000 }) },
  sentimentScoreText(text) { return api.post('/api/sentiment/score', { text }) },
}
