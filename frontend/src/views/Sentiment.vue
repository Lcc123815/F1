<template>
  <div class="sent-page">
    <!-- 顶部状态条 -->
    <div class="status-bar">
      <div>
        <span class="brand">舆情情感分析</span>
        <span class="muted"> · 数据源：东方财富个股新闻</span>
      </div>
      <div>
        <el-tag v-if="status.hf_available" type="success" effect="dark">HF 模型已加载：{{ status.model }}</el-tag>
        <el-tag v-else type="warning" effect="dark">词典模式（未安装 transformers/torch）</el-tag>
      </div>
    </div>

    <!-- 控制面板 -->
    <el-card class="panel" shadow="never">
      <el-form :model="form" inline>
        <el-form-item label="股票">
          <el-select v-model="form.code" filterable placeholder="选择或输入代码" style="width:240px"
                     @change="onCodeChange">
            <el-option v-for="s in poolOptions" :key="s.code"
                       :label="`${s.code} ${s.name}`" :value="s.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-select v-model="form.days" style="width:120px">
            <el-option label="近 3 天" :value="3" />
            <el-option label="近 7 天" :value="7" />
            <el-option label="近 15 天" :value="15" />
            <el-option label="近 30 天" :value="30" />
          </el-select>
        </el-form-item>
        <el-form-item label="新闻条数">
          <el-input-number v-model="form.limit" :min="5" :max="100" :step="5" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadOne" :loading="loading">分析</el-button>
          <el-button @click="loadBatch" :loading="batchLoading">核心池排行</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 单股分析结果 -->
    <el-row :gutter="14" style="margin-top:14px">
      <el-col :span="6">
        <div class="kpi">
          <div class="lbl">综合情感得分</div>
          <div class="val" :class="scoreColor(summary.score)">
            {{ summary.score.toFixed(3) }}
          </div>
          <div class="sub">{{ summary.label }} · 共 {{ summary.count }} 条</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi">
          <div class="lbl">正面占比</div>
          <div class="val up">{{ (summary.pos_ratio * 100).toFixed(1) }}%</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi">
          <div class="lbl">中性占比</div>
          <div class="val">{{ (summary.neu_ratio * 100).toFixed(1) }}%</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="kpi">
          <div class="lbl">负面占比</div>
          <div class="val down">{{ (summary.neg_ratio * 100).toFixed(1) }}%</div>
        </div>
      </el-col>
    </el-row>

    <!-- 主区：趋势图 + 新闻表 -->
    <el-row :gutter="14" style="margin-top:14px">
      <el-col :span="14">
        <el-card class="panel" shadow="never">
          <div class="panel-title">每日舆情得分趋势</div>
          <div ref="trendRef" style="width:100%;height:340px"></div>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card class="panel" shadow="never">
          <div class="panel-title">分布直方图</div>
          <div ref="histRef" style="width:100%;height:340px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 新闻明细 -->
    <el-card class="panel" shadow="never" style="margin-top:14px">
      <div class="panel-title">
        新闻明细
        <span class="muted">（点击标题打开原文）</span>
      </div>
      <el-table :data="news" size="small" stripe>
        <el-table-column prop="time" label="时间" width="160" />
        <el-table-column label="标题" min-width="380">
          <template #default="{ row }">
            <a :href="row.url" target="_blank" rel="noopener" class="news-title">
              {{ row.title }}
            </a>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="120" />
        <el-table-column label="得分" width="100">
          <template #default="{ row }">
            <span :class="scoreColor(row.score)">{{ row.score.toFixed(3) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="模式" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.mode === 'hf' ? 'success' : 'info'">{{ row.mode }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 批量排行榜 -->
    <el-card v-if="batch.length" class="panel" shadow="never" style="margin-top:14px">
      <div class="panel-title">核心池舆情排行榜</div>
      <el-table :data="batch" size="small" stripe>
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="code" label="代码" width="100" />
        <el-table-column label="情感得分" width="120">
          <template #default="{ row }">
            <span :class="scoreColor(row.summary.score)">{{ row.summary.score.toFixed(3) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="标签" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="tagType(row.summary.label)">{{ row.summary.label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="正/中/负" width="160">
          <template #default="{ row }">
            <span class="up">{{ (row.summary.pos_ratio*100).toFixed(0) }}%</span> /
            {{ (row.summary.neu_ratio*100).toFixed(0) }}% /
            <span class="down">{{ (row.summary.neg_ratio*100).toFixed(0) }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary.count" label="样本" width="80" />
        <el-table-column label="代表新闻">
          <template #default="{ row }">
            <div v-for="(t, i) in row.sample_titles" :key="i" class="news-snip">{{ t }}</div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import api from '@/api'

const status = reactive({ hf_available: false, model: '' })
const poolOptions = ref([])
const form = reactive({ code: '', days: 7, limit: 30 })
const loading = ref(false)
const batchLoading = ref(false)

const news = ref([])
const trend = ref([])
const summary = reactive({ score: 0, label: '中性', pos_ratio: 0, neu_ratio: 0, neg_ratio: 0, count: 0 })
const batch = ref([])

const trendRef = ref(null)
const histRef = ref(null)
let trendChart, histChart

function scoreColor(s) { return s > 0.15 ? 'up' : s < -0.15 ? 'down' : 'neu' }
function tagType(label) {
  return label === '看多' ? 'danger' : label === '看空' ? 'success' : 'info'
}

async function loadStatus() {
  try {
    const { data } = await api.sentimentStatus()
    Object.assign(status, data.data)
  } catch {}
}

async function loadPool() {
  try {
    const { data } = await api.poolList({ category: 'all', page: 1, size: 200 })
    poolOptions.value = (data.data?.list || []).map(s => ({ code: s.code, name: s.name, category: s.category }))
    if (!form.code && poolOptions.value.length) form.code = poolOptions.value[0].code
  } catch {}
}

function onCodeChange() { /* 留给用户手动点击"分析"，避免误触发抓新闻 */ }

async function loadOne() {
  if (!form.code) { ElMessage.warning('请先选择股票'); return }
  loading.value = true
  try {
    const { data } = await api.sentimentNews(form.code, form.days, form.limit)
    const d = data.data || {}
    news.value = d.items || []
    trend.value = d.trend || []
    Object.assign(summary, d.summary || {})
    await nextTick()
    renderTrend()
    renderHist()
    if (!news.value.length) ElMessage.info('该时间窗口内未抓到新闻')
  } catch (e) {
    ElMessage.error('抓取失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function loadBatch() {
  const codes = poolOptions.value.filter(p => p.category === 'core').map(p => p.code).slice(0, 12)
  if (!codes.length) { ElMessage.warning('核心池为空'); return }
  batchLoading.value = true
  try {
    const { data } = await api.sentimentBatch(codes, form.days, 15)
    batch.value = (data.data || []).map(r => {
      const opt = poolOptions.value.find(p => p.code === r.code)
      return { ...r, name: opt?.name || '' }
    })
  } catch (e) {
    ElMessage.error('批量分析失败：' + (e.response?.data?.detail || e.message))
  } finally {
    batchLoading.value = false
  }
}

function renderTrend() {
  if (!trendRef.value) return
  trendChart = trendChart || echarts.init(trendRef.value)
  const dates = trend.value.map(t => t.date)
  const scores = trend.value.map(t => t.score)
  const counts = trend.value.map(t => t.count)
  trendChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { textStyle: { color: '#94a3b8' }, top: 0 },
    grid: { left: 50, right: 50, top: 36, bottom: 30 },
    xAxis: { type: 'category', data: dates, axisLine:{lineStyle:{color:'#334155'}}, axisLabel:{color:'#94a3b8'} },
    yAxis: [
      { type:'value', name:'得分', min:-1, max:1, axisLine:{lineStyle:{color:'#334155'}}, axisLabel:{color:'#94a3b8'}, splitLine:{lineStyle:{color:'#1e293b'}} },
      { type:'value', name:'条数', axisLine:{lineStyle:{color:'#334155'}}, axisLabel:{color:'#94a3b8'} },
    ],
    series: [
      {
        name: '日均得分', type: 'line', smooth: true, data: scores,
        lineStyle: { width: 2 }, itemStyle:{ color:'#0ea5e9' },
        markLine: { symbol:'none', lineStyle:{color:'#475569'}, data:[{yAxis:0}] },
        areaStyle: { color: { type:'linear', x:0,y:0,x2:0,y2:1, colorStops:[
          {offset:0, color:'rgba(14,165,233,0.35)'}, {offset:1, color:'rgba(14,165,233,0)'}
        ]}}
      },
      { name: '新闻条数', type: 'bar', yAxisIndex: 1, data: counts, barMaxWidth: 14, itemStyle:{ color:'#7c3aed', opacity:0.6 } },
    ],
  }, true)
}

function renderHist() {
  if (!histRef.value) return
  histChart = histChart || echarts.init(histRef.value)
  const bins = [-1, -0.6, -0.3, -0.1, 0.1, 0.3, 0.6, 1.0001]
  const labels = ['强烈负','负面','偏负','中性','偏正','正面','强烈正']
  const counts = new Array(labels.length).fill(0)
  news.value.forEach(n => {
    for (let i = 0; i < labels.length; i++) {
      if (n.score >= bins[i] && n.score < bins[i+1]) { counts[i]++; break }
    }
  })
  const colors = ['#15803d','#22c55e','#86efac','#64748b','#fca5a5','#ef4444','#991b1b']
  histChart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger:'axis' },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: { type:'category', data: labels, axisLine:{lineStyle:{color:'#334155'}}, axisLabel:{color:'#94a3b8'} },
    yAxis: { type:'value', axisLine:{lineStyle:{color:'#334155'}}, axisLabel:{color:'#94a3b8'}, splitLine:{lineStyle:{color:'#1e293b'}} },
    series: [{
      type: 'bar', data: counts.map((c,i)=>({value:c, itemStyle:{color:colors[i]}})),
      barMaxWidth: 30, label:{show:true, position:'top', color:'#cbd5e1'},
    }],
  }, true)
}

onMounted(async () => {
  await loadStatus()
  await loadPool()
})
</script>

<style scoped>
.sent-page { padding: 4px; }
.status-bar {
  display:flex; justify-content:space-between; align-items:center;
  padding: 10px 16px; margin-bottom: 12px;
  background: #0f172a; border:1px solid #1e293b; border-radius: 8px;
}
.brand { color:#e2e8f0; font-size: 16px; font-weight: 700; }
.muted { color:#64748b; font-size: 12px; }

.panel { background:#0f172a; border:1px solid #1e293b; }
.panel-title { color:#e2e8f0; font-size: 14px; font-weight: 600; margin-bottom: 8px; }

.kpi {
  background:#0f172a; border:1px solid #1e293b; border-radius:8px;
  padding: 14px 18px; height: 92px; display:flex; flex-direction:column; justify-content:center;
}
.kpi .lbl { color:#94a3b8; font-size:12px; }
.kpi .val { font-size:24px; font-weight:700; margin-top:4px; color:#e2e8f0; }
.kpi .sub { color:#64748b; font-size:11px; margin-top:2px; }

.up { color:#ef4444 !important; }
.down { color:#22c55e !important; }
.neu { color:#cbd5e1 !important; }

.news-title { color:#cbd5e1; text-decoration:none; }
.news-title:hover { color:#0ea5e9; text-decoration:underline; }
.news-snip { color:#94a3b8; font-size:12px; margin: 2px 0; line-height:1.4; }

:deep(.el-card__body) { background:#0f172a; }
:deep(.el-table),
:deep(.el-table__inner-wrapper),
:deep(.el-table tr),
:deep(.el-table__body),
:deep(.el-table__body tr.el-table__row),
:deep(.el-table__body tr.el-table__row td.el-table__cell) {
  background-color: #0f172a !important;
  color: #cbd5e1;
}
:deep(.el-table) {
  --el-table-bg-color: #0f172a;
  --el-table-tr-bg-color: #0f172a;
  --el-table-row-hover-bg-color: #1e293b;
  --el-table-border-color: #1e293b;
  --el-table-header-bg-color: #0b1220;
  --el-table-header-text-color: #94a3b8;
  --el-fill-color-lighter: #131c30;     /* 斑马纹偶数行 */
  --el-fill-color-light: #131c30;
}
:deep(.el-table th.el-table__cell) { background:#0b1220 !important; color:#94a3b8 !important; }
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) {
  background-color: #131c30 !important;
}
:deep(.el-table__body tr:hover > td.el-table__cell) {
  background-color: #1e293b !important;
}
:deep(.el-form-item__label) { color:#cbd5e1; }
</style>
