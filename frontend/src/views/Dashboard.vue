<template>
  <div class="dashboard">
    <!-- 顶部标题栏 -->
    <div class="header">
      <div class="title-area">
        <div class="brand">FinQuantDash · 实时量化数据大屏</div>
        <div class="subtitle">
          <span class="dot" :class="{ live: marketOpen }"></span>
          <span>{{ marketStatusText }}</span>
          <span class="divider">|</span>
          <span>{{ nowText }}</span>
          <span class="divider">|</span>
          <span>样本池 {{ stats.total }} 只 · 核心 {{ stats.core }} · 普通 {{ stats.general }} · 黑名单 {{ stats.black }}</span>
        </div>
      </div>
      <div class="actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" inline-prompt />
        <el-button :icon="Refresh" circle @click="loadAll" :loading="loading" />
      </div>
    </div>

    <!-- KPI 指标卡 -->
    <el-row :gutter="14" class="kpi-row">
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">上涨家数</div>
        <div class="kpi-value up">{{ kpi.upCount }}</div>
        <div class="kpi-sub">占比 {{ kpi.upRatio }}%</div>
      </div></el-col>
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">下跌家数</div>
        <div class="kpi-value down">{{ kpi.downCount }}</div>
        <div class="kpi-sub">占比 {{ kpi.downRatio }}%</div>
      </div></el-col>
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">平均涨跌幅</div>
        <div class="kpi-value" :class="kpi.avgChg >= 0 ? 'up' : 'down'">{{ kpi.avgChg.toFixed(2) }}%</div>
        <div class="kpi-sub">中位数 {{ kpi.medChg.toFixed(2) }}%</div>
      </div></el-col>
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">总成交额</div>
        <div class="kpi-value">{{ formatBillion(kpi.totalAmount) }}</div>
        <div class="kpi-sub">亿元</div>
      </div></el-col>
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">最高涨幅</div>
        <div class="kpi-value up">{{ kpi.topUp ? kpi.topUp.pct.toFixed(2) + '%' : '-' }}</div>
        <div class="kpi-sub">{{ kpi.topUp ? kpi.topUp.name : '' }}</div>
      </div></el-col>
      <el-col :span="4"><div class="kpi-card">
        <div class="kpi-label">最大跌幅</div>
        <div class="kpi-value down">{{ kpi.topDown ? kpi.topDown.pct.toFixed(2) + '%' : '-' }}</div>
        <div class="kpi-sub">{{ kpi.topDown ? kpi.topDown.name : '' }}</div>
      </div></el-col>
    </el-row>

    <!-- 第二行：分布饼图 + 涨跌榜 + 资金条形图 -->
    <el-row :gutter="14" class="row-block">
      <el-col :span="6"><div class="panel">
        <div class="panel-title">市场涨跌分布</div>
        <div ref="chgPieRef" class="chart-h-260"></div>
      </div></el-col>
      <el-col :span="6"><div class="panel">
        <div class="panel-title">行业分布 TOP 8</div>
        <div ref="indPieRef" class="chart-h-260"></div>
      </div></el-col>
      <el-col :span="6"><div class="panel">
        <div class="panel-title">涨幅榜 TOP 5</div>
        <el-table :data="topUpList" size="small" :show-header="false" class="rank-table">
          <el-table-column type="index" width="32" />
          <el-table-column prop="name" />
          <el-table-column prop="code" width="70" />
          <el-table-column width="80">
            <template #default="{ row }"><span class="up">+{{ row.pct.toFixed(2) }}%</span></template>
          </el-table-column>
        </el-table>
      </div></el-col>
      <el-col :span="6"><div class="panel">
        <div class="panel-title">跌幅榜 TOP 5</div>
        <el-table :data="topDownList" size="small" :show-header="false" class="rank-table">
          <el-table-column type="index" width="32" />
          <el-table-column prop="name" />
          <el-table-column prop="code" width="70" />
          <el-table-column width="80">
            <template #default="{ row }"><span class="down">{{ row.pct.toFixed(2) }}%</span></template>
          </el-table-column>
        </el-table>
      </div></el-col>
    </el-row>

    <!-- 第三行：行业涨跌 + 成交额 TOP10 -->
    <el-row :gutter="14" class="row-block">
      <el-col :span="12"><div class="panel">
        <div class="panel-title">行业平均涨跌幅</div>
        <div ref="indBarRef" class="chart-h-300"></div>
      </div></el-col>
      <el-col :span="12"><div class="panel">
        <div class="panel-title">成交额 TOP 10</div>
        <div ref="amtBarRef" class="chart-h-300"></div>
      </div></el-col>
    </el-row>

    <!-- 第四行：核心池K线对比 -->
    <el-row :gutter="14" class="row-block">
      <el-col :span="16"><div class="panel">
        <div class="panel-title">
          核心池近 60 日累计收益对比
          <span class="hint">（基期归一化为 1.00）</span>
        </div>
        <div ref="netChartRef" class="chart-h-360" v-loading="klineLoading"></div>
      </div></el-col>
      <el-col :span="8"><div class="panel">
        <div class="panel-title">核心池实时行情</div>
        <el-table :data="coreList" size="small" height="360">
          <el-table-column prop="code" label="代码" width="80" />
          <el-table-column prop="name" label="名称" />
          <el-table-column label="价格" width="80">
            <template #default="{ row }">{{ row.price?.toFixed(2) ?? '-' }}</template>
          </el-table-column>
          <el-table-column label="涨跌" width="90">
            <template #default="{ row }">
              <span :class="row.pct >= 0 ? 'up' : 'down'">{{ row.pct >= 0 ? '+' : '' }}{{ row.pct.toFixed(2) }}%</span>
            </template>
          </el-table-column>
        </el-table>
      </div></el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'

// ============== 状态 ==============
const loading = ref(false)
const klineLoading = ref(false)
const autoRefresh = ref(true)
const nowText = ref('')
const stats = reactive({ total: 0, core: 0, general: 0, black: 0 })
const allRows = ref([])           // 全量股票池(含行情)
const coreList = ref([])          // 核心池含 pct
const topUpList = ref([])
const topDownList = ref([])
const kpi = reactive({
  upCount: 0, downCount: 0, upRatio: 0, downRatio: 0,
  avgChg: 0, medChg: 0, totalAmount: 0,
  topUp: null, topDown: null,
})

// chart refs
const chgPieRef = ref(null)
const indPieRef = ref(null)
const indBarRef = ref(null)
const amtBarRef = ref(null)
const netChartRef = ref(null)
const charts = {}

// ============== 时间 / 市场 ==============
function tick() {
  const d = new Date()
  const pad = n => String(n).padStart(2, '0')
  nowText.value = `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
const marketOpen = computed(() => {
  const d = new Date(); const dow = d.getDay(); const m = d.getHours()*60 + d.getMinutes()
  if (dow === 0 || dow === 6) return false
  return (m >= 570 && m <= 690) || (m >= 780 && m <= 900)
})
const marketStatusText = computed(() => marketOpen.value ? 'A股交易中' : '休市中')

// ============== 工具 ==============
function formatBillion(amount) {
  if (!amount) return '0.00'
  return (amount / 1e8).toFixed(2)
}
function median(arr) {
  if (!arr.length) return 0
  const s = [...arr].sort((a,b)=>a-b); const m = Math.floor(s.length/2)
  return s.length % 2 ? s[m] : (s[m-1]+s[m])/2
}

// ============== 数据加载 ==============
async function loadPool() {
  loading.value = true
  try {
    // 拉取全量（一次取较大 size，简化）
    // 受 iTick 5次/分钟 限制，仅拉取核心+部分普通池（约 30 只）做大屏聚合
    const { data: res } = await api.poolList({ category: 'all', page: 1, size: 30 })
    const counts = res.data.counts || {}
    stats.total = counts.all || 0
    stats.core = counts.core || 0
    stats.general = counts.general || 0
    stats.black = counts.blacklist || 0
    const list = (res.data.list || []).map(r => {
      const price = r.price ?? null
      const open = r.open ?? null
      const pct = price && open ? (price - open) / open * 100 : 0
      return { ...r, pct }
    })
    allRows.value = list
    computeKpi(list)
    renderPies(list)
    renderIndBar(list)
    renderAmtBar(list)
    coreList.value = list.filter(r => r.category === 'core')
    topUpList.value = [...list].sort((a,b)=>b.pct-a.pct).slice(0,5)
    topDownList.value = [...list].sort((a,b)=>a.pct-b.pct).slice(0,5)
  } catch (e) {
    console.error('loadPool failed', e)
  } finally {
    loading.value = false
  }
}

function computeKpi(list) {
  const tradable = list.filter(r => r.category !== 'blacklist' && r.price && r.open)
  const ups = tradable.filter(r => r.pct > 0)
  const downs = tradable.filter(r => r.pct < 0)
  kpi.upCount = ups.length
  kpi.downCount = downs.length
  const denom = tradable.length || 1
  kpi.upRatio = (ups.length / denom * 100).toFixed(1)
  kpi.downRatio = (downs.length / denom * 100).toFixed(1)
  const chgs = tradable.map(r => r.pct)
  kpi.avgChg = chgs.length ? chgs.reduce((a,b)=>a+b,0)/chgs.length : 0
  kpi.medChg = median(chgs)
  kpi.totalAmount = tradable.reduce((s,r)=> s + (r.turnover||0), 0)
  kpi.topUp = tradable.length ? [...tradable].sort((a,b)=>b.pct-a.pct)[0] : null
  kpi.topDown = tradable.length ? [...tradable].sort((a,b)=>a.pct-b.pct)[0] : null
}

// ============== 图表渲染 ==============
const baseGrid = { left: 50, right: 20, top: 30, bottom: 30 }
const axisStyle = {
  axisLine: { lineStyle: { color: '#334155' } },
  axisLabel: { color: '#94a3b8' },
  splitLine: { lineStyle: { color: '#1e293b' } },
}

function getOrInit(refEl, key) {
  if (!refEl) return null
  if (!charts[key] || charts[key].isDisposed?.()) {
    charts[key] = echarts.init(refEl)
  }
  return charts[key]
}

function renderPies(list) {
  const tradable = list.filter(r => r.category !== 'blacklist' && r.price && r.open)
  const up = tradable.filter(r=>r.pct>0).length
  const down = tradable.filter(r=>r.pct<0).length
  const flat = tradable.length - up - down
  const pie1 = getOrInit(chgPieRef.value, 'chgPie')
  pie1?.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { color: '#94a3b8' } },
    series: [{
      type: 'pie', radius: ['45%','70%'], center: ['50%','45%'],
      label: { color: '#e2e8f0', formatter: '{b}\n{c}' },
      data: [
        { name: '上涨', value: up, itemStyle:{color:'#ef4444'}},
        { name: '下跌', value: down, itemStyle:{color:'#22c55e'}},
        { name: '平盘', value: flat, itemStyle:{color:'#64748b'}},
      ],
    }],
  })
  // 行业分布 TOP 8
  const map = new Map()
  list.forEach(r => map.set(r.industry||'未分类', (map.get(r.industry||'未分类')||0)+1))
  const industries = [...map.entries()].sort((a,b)=>b[1]-a[1]).slice(0,8)
  const pie2 = getOrInit(indPieRef.value, 'indPie')
  pie2?.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    legend: { type:'scroll', bottom: 0, textStyle: { color: '#94a3b8' } },
    series: [{
      type: 'pie', radius: ['40%','68%'], center: ['50%','45%'], roseType: 'radius',
      label: { color: '#e2e8f0' },
      data: industries.map(([n,v])=>({name:n,value:v})),
    }],
  })
}

function renderIndBar(list) {
  const tradable = list.filter(r => r.category !== 'blacklist' && r.price && r.open)
  const map = new Map()
  tradable.forEach(r => {
    const k = r.industry || '未分类'
    const arr = map.get(k) || []
    arr.push(r.pct); map.set(k, arr)
  })
  const data = [...map.entries()]
    .map(([n, arr])=>({name:n, avg: arr.reduce((a,b)=>a+b,0)/arr.length}))
    .sort((a,b)=>b.avg-a.avg)
  const c = getOrInit(indBarRef.value, 'indBar')
  c?.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type:'shadow' }, valueFormatter: v=>v.toFixed(2)+'%' },
    grid: { ...baseGrid, left: 90 },
    xAxis: { type: 'value', ...axisStyle, axisLabel:{...axisStyle.axisLabel, formatter:'{value}%'} },
    yAxis: { type: 'category', data: data.map(d=>d.name), ...axisStyle, inverse: true },
    series: [{
      type: 'bar',
      data: data.map(d => ({ value: d.avg.toFixed(2), itemStyle:{ color: d.avg>=0?'#ef4444':'#22c55e' } })),
      label: { show:true, position:'right', color:'#e2e8f0', formatter:'{c}%' },
      barMaxWidth: 14,
    }],
  })
}

function renderAmtBar(list) {
  const top = [...list].filter(r=>r.turnover).sort((a,b)=>b.turnover-a.turnover).slice(0,10)
  const c = getOrInit(amtBarRef.value, 'amtBar')
  c?.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type:'shadow' }, valueFormatter: v=>(v/1e8).toFixed(2)+' 亿元' },
    grid: { ...baseGrid, left: 90 },
    xAxis: { type: 'value', ...axisStyle, axisLabel: {...axisStyle.axisLabel, formatter: v=>(v/1e8).toFixed(1)+'亿'} },
    yAxis: { type:'category', data: top.map(r=>r.name), ...axisStyle, inverse: true },
    series: [{
      type: 'bar',
      data: top.map(r => r.turnover),
      itemStyle: {
        color: { type:'linear', x:0, y:0, x2:1, y2:0, colorStops:[
          {offset:0,color:'#0ea5e9'},{offset:1,color:'#a855f7'}
        ]},
      },
      barMaxWidth: 14,
    }],
  })
}

// ============== 核心池 K 线对比 ==============
async function loadCoreKline() {
  const targets = coreList.value.slice(0, 6)
  if (!targets.length) return
  klineLoading.value = true
  try {
    const results = await Promise.all(targets.map(t =>
      api.itickKline(t.code, 8, 60).then(r => ({ t, kl: r.data?.data || [] })).catch(()=>({t,kl:[]}))
    ))
    const series = []
    let xLabels = []
    results.forEach(({ t, kl }) => {
      if (!kl.length) return
      const sorted = [...kl].sort((a,b)=> (a.t||0) - (b.t||0))
      const closes = sorted.map(k => k.c)
      const base = closes[0]
      const norm = closes.map(c => +(c / base).toFixed(4))
      const dates = sorted.map(k => {
        const d = new Date(k.t)
        return `${d.getMonth()+1}/${d.getDate()}`
      })
      if (dates.length > xLabels.length) xLabels = dates
      series.push({
        name: t.name, type: 'line', smooth: true, showSymbol: false,
        data: norm, lineStyle: { width: 1.6 },
      })
    })
    const c = getOrInit(netChartRef.value, 'net')
    c?.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: { textStyle: { color: '#94a3b8' }, top: 0 },
      grid: { ...baseGrid, top: 40 },
      xAxis: { type:'category', data: xLabels, ...axisStyle },
      yAxis: { type:'value', scale:true, ...axisStyle },
      series,
    }, true)
  } finally {
    klineLoading.value = false
  }
}

// ============== 生命周期 ==============
let clockTimer = null
let refreshTimer = null

async function loadAll() {
  await loadPool()
  await loadCoreKline()
}

onMounted(async () => {
  tick()
  clockTimer = setInterval(tick, 1000)
  await nextTick()
  await loadAll()
  // 5 分钟刷新一次（与 iTick 5次/分钟 配额对齐，避免触发 429）
  refreshTimer = setInterval(() => { if (autoRefresh.value) loadAll() }, 5 * 60_000)
  window.addEventListener('resize', resizeAll)
})

onBeforeUnmount(() => {
  clearInterval(clockTimer)
  clearInterval(refreshTimer)
  window.removeEventListener('resize', resizeAll)
  Object.values(charts).forEach(c => c?.dispose?.())
})

function resizeAll() {
  Object.values(charts).forEach(c => c?.resize?.())
}

watch(coreList, () => { loadCoreKline() })
</script>

<style scoped>
.dashboard { padding: 4px 6px 24px; }

.header {
  display:flex; justify-content:space-between; align-items:center;
  padding: 10px 16px; margin-bottom: 14px;
  background: linear-gradient(90deg, #0b1220 0%, #0f172a 60%, #0b1220 100%);
  border: 1px solid #1e293b; border-radius: 8px;
}
.brand { color:#e2e8f0; font-size: 18px; font-weight: 700; letter-spacing: 1px; }
.subtitle { color:#94a3b8; font-size: 12px; margin-top: 4px; display:flex; align-items:center; gap:8px; }
.divider { color:#334155; }
.dot { width:8px;height:8px;border-radius:50%;background:#64748b;display:inline-block; }
.dot.live { background:#22c55e; box-shadow:0 0 8px #22c55e; animation: pulse 1.6s infinite; }
@keyframes pulse { 0%,100%{opacity:1}50%{opacity:.4} }
.actions { display:flex; align-items:center; gap:12px; }

.kpi-row { margin-bottom: 14px; }
.kpi-card {
  background: linear-gradient(160deg,#0f172a,#0b1220);
  border:1px solid #1e293b; border-radius: 8px; padding: 14px 16px;
  height: 92px; display:flex; flex-direction:column; justify-content:center;
}
.kpi-label { color:#94a3b8; font-size: 12px; }
.kpi-value { color:#e2e8f0; font-size: 24px; font-weight: 700; margin-top: 4px; }
.kpi-sub { color:#64748b; font-size: 11px; margin-top: 2px; }
.up { color:#ef4444 !important; }
.down { color:#22c55e !important; }

.row-block { margin-bottom: 14px; }
.panel {
  background:#0f172a; border:1px solid #1e293b; border-radius: 8px;
  padding: 12px 14px; height: 100%;
}
.panel-title {
  color:#e2e8f0; font-size: 14px; font-weight: 600; margin-bottom: 6px;
  display:flex; align-items:center; gap:6px;
}
.panel-title .hint { color:#64748b; font-size: 11px; font-weight: 400; }
.chart-h-260 { width:100%; height: 260px; }
.chart-h-300 { width:100%; height: 300px; }
.chart-h-360 { width:100%; height: 360px; }

.rank-table { background: transparent; }
:deep(.rank-table tr), :deep(.rank-table td) { background: transparent !important; color:#cbd5e1; }
:deep(.rank-table .el-table__inner-wrapper::before) { display:none; }
:deep(.el-table) { --el-table-bg-color: transparent; --el-table-tr-bg-color: transparent; --el-table-row-hover-bg-color:#1e293b; --el-table-border-color:#1e293b; color:#cbd5e1; }
:deep(.el-table th.el-table__cell) { background:#0b1220 !important; color:#94a3b8 !important; }
</style>
