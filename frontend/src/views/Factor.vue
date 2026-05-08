<template>
  <div>
    <!-- 配置 -->
    <el-card style="background:#0f172a;border:1px solid #1e293b">
      <h3 style="color:#e2e8f0;margin:0 0 12px 0">因子分析（量价因子 IC + PCA 降维）</h3>
      <el-form :model="form" inline label-position="top">
        <el-form-item label="股票池">
          <el-select v-model="form.use_pool" style="width:140px">
            <el-option label="核心池" value="core" />
            <el-option label="普通池" value="general" />
            <el-option label="全部" value="all" />
          </el-select>
        </el-form-item>
        <el-form-item label="股票数上限">
          <el-input-number v-model="form.max_codes" :min="3" :max="30" style="width:120px" />
        </el-form-item>
        <el-form-item label="因子（多选）">
          <el-select v-model="form.factor_keys" multiple collapse-tags collapse-tags-tooltip style="min-width:280px">
            <el-option v-for="f in factorMeta" :key="f.key" :label="f.name" :value="f.key">
              <span>{{ f.name }}</span>
              <span style="color:#94a3b8;font-size:12px;margin-left:8px">{{ f.description }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="预测周期(日)">
          <el-input-number v-model="form.horizon" :min="1" :max="20" style="width:120px" />
        </el-form-item>
        <el-form-item label="K 线根数">
          <el-input-number v-model="form.limit" :min="60" :max="500" :step="50" style="width:120px" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="loading" @click="onRun">开始分析</el-button>
          <span v-if="loading" style="color:#94a3b8;margin-left:8px;font-size:12px">{{ loadingHint || '分析中...' }}</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-tabs v-if="result" v-model="tab" style="margin-top:12px" type="card">
      <!-- IC 分析 -->
      <el-tab-pane label="单因子 IC 分析" name="ic">
        <el-table :data="result.ic.factors" border
          :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }"
          :cell-style="{ background:'#0f172a', color:'#cbd5e1' }">
          <el-table-column label="因子" prop="name" />
          <el-table-column label="IC 均值" align="right">
            <template #default="{ row }">
              <span :style="{ color: row.ic_mean > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }">
                {{ row.ic_mean.toFixed(4) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="IC 标准差" prop="ic_std" align="right" />
          <el-table-column label="IR 信息比" prop="ir" align="right" />
          <el-table-column label="t 统计量" align="right">
            <template #default="{ row }">
              <span :style="{ color: Math.abs(row.t_stat) >= 2 ? '#fbbf24' : '#cbd5e1', fontWeight: Math.abs(row.t_stat) >= 2 ? 600 : 400 }">
                {{ row.t_stat.toFixed(2) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="胜率" align="right">
            <template #default="{ row }">{{ (row.win_rate * 100).toFixed(1) }}%</template>
          </el-table-column>
          <el-table-column label="样本期" prop="n_periods" align="right" />
          <el-table-column label="评价" align="center">
            <template #default="{ row }">
              <el-tag :type="evalTag(row).type">{{ evalTag(row).label }}</el-tag>
            </template>
          </el-table-column>
        </el-table>

        <el-row :gutter="12" style="margin-top:12px">
          <el-col :span="12">
            <el-card style="background:#0f172a;border:1px solid #1e293b">
              <template #header><span style="color:#fff">分组累积收益（最佳因子，5 分组）</span></template>
              <v-chart :option="groupOption" style="height:340px" autoresize />
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card style="background:#0f172a;border:1px solid #1e293b">
              <template #header><span style="color:#fff">IC 时序（最佳因子）</span></template>
              <v-chart :option="icSeriesOption" style="height:340px" autoresize />
            </el-card>
          </el-col>
        </el-row>

        <el-card style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
          <template #header><span style="color:#fff">IC 热力图（因子 × 日期，最近 60 天）</span></template>
          <v-chart :option="heatmapOption" style="height:280px" autoresize />
        </el-card>
      </el-tab-pane>

      <!-- PCA -->
      <el-tab-pane label="PCA 降维" name="pca">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-card style="background:#0f172a;border:1px solid #1e293b">
              <template #header><span style="color:#fff">碎石图（Scree Plot）</span></template>
              <v-chart :option="screeOption" style="height:320px" autoresize />
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card style="background:#0f172a;border:1px solid #1e293b">
              <template #header><span style="color:#fff">载荷热力图（因子 → 主成分）</span></template>
              <v-chart :option="loadingsOption" style="height:320px" autoresize />
            </el-card>
          </el-col>
        </el-row>

        <el-card style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
          <template #header>
            <span style="color:#fff">主成分构成</span>
            <span style="color:#94a3b8;margin-left:12px;font-size:12px">
              累计方差解释率：{{ (result.pca.components[result.pca.components.length-1].cumulative * 100).toFixed(1) }}%
            </span>
          </template>
          <el-table :data="result.pca.components" border size="small"
            :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }"
            :cell-style="{ background:'#0f172a', color:'#cbd5e1' }">
            <el-table-column label="主成分" prop="name" width="80" />
            <el-table-column label="特征根" prop="eigenvalue" width="100" align="right" />
            <el-table-column label="方差解释率" align="right" width="120">
              <template #default="{ row }">{{ (row.explained_ratio * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="累计解释率" align="right" width="120">
              <template #default="{ row }">{{ (row.cumulative * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="主导因子（载荷绝对值最大）">
              <template #default="{ row }">{{ topLoading(row.loadings) }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
          <template #header><span style="color:#fff">综合得分排名（PCA 加权综合评分）</span></template>
          <el-table :data="result.pca.ranking" border size="small"
            :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }"
            :cell-style="{ background:'#0f172a', color:'#cbd5e1' }">
            <el-table-column type="index" label="排名" width="60" />
            <el-table-column label="代码" prop="code" width="100" />
            <el-table-column label="综合得分" align="right">
              <template #default="{ row }">
                <span :style="{ color: row.composite_score > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }">
                  {{ row.composite_score.toFixed(4) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column v-for="c in result.pca.components" :key="c.name" :label="c.name" :prop="c.name" align="right" />
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart, BarChart, HeatmapChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, DataZoomComponent } from 'echarts/components'
import api from '@/api'

use([CanvasRenderer, LineChart, BarChart, HeatmapChart, GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, DataZoomComponent])

const factorMeta = ref([])
const form = reactive({
  use_pool: 'core',
  max_codes: 8,
  factor_keys: ['momentum_20', 'reversal_5', 'volatility', 'liquidity', 'volume_mom'],
  horizon: 5,
  limit: 150,
})
const loading = ref(false)
const loadingHint = ref('')
const result = ref(null)
const tab = ref('ic')

function evalTag(f) {
  const t = Math.abs(f.t_stat)
  const ic = Math.abs(f.ic_mean)
  if (t >= 2 && ic >= 0.05) return { type: 'success', label: '显著有效' }
  if (t >= 1.5) return { type: 'warning', label: '弱有效' }
  return { type: 'info', label: '不显著' }
}

function topLoading(loadings) {
  const entries = Object.entries(loadings).map(([k, v]) => [k, v])
  entries.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
  return entries.slice(0, 2).map(([k, v]) => `${k}(${v.toFixed(3)})`).join(', ')
}

async function loadFactors() {
  try {
    const { data } = await api.factorList()
    factorMeta.value = data.data
  } catch (e) { ElMessage.error('加载因子列表失败') }
}

async function onRun() {
  if (!form.factor_keys.length) return ElMessage.warning('请至少选择一个因子')
  loading.value = true
  loadingHint.value = '正在评估缓存命中情况...'
  try {
    // 先取候选代码并查缓存命中，预估真实耗时
    try {
      const { data: pool } = await api.poolList({ category: form.use_pool === 'all' ? 'all' : form.use_pool, page: 1, size: form.max_codes })
      const candidate = (pool.data?.list || []).map(r => r.code).slice(0, form.max_codes)
      if (candidate.length) {
        const { data: cs } = await api.factorCacheStatus(candidate.join(','), form.limit)
        const d = cs.data || {}
        if (d.miss === 0) {
          loadingHint.value = '缓存全部命中，秒级返回...'
        } else {
          loadingHint.value = `${d.fresh}只新鲜 / ${d.stale}只陈旧 / ${d.miss}只待拉取，预计 ${d.estimate_seconds}s（受 iTick 5次/分钟 限制）`
        }
      }
    } catch {}
    const { data } = await api.factorAnalyze({ ...form })
    result.value = data.data
    ElMessage.success(`分析完成（${result.value.codes_used.length} 只股票）`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分析失败')
  } finally {
    loading.value = false
    loadingHint.value = ''
  }
}

const bestFactor = computed(() => {
  if (!result.value) return null
  return [...result.value.ic.factors].sort((a, b) => Math.abs(b.t_stat) - Math.abs(a.t_stat))[0]
})

const groupOption = computed(() => {
  const f = bestFactor.value
  if (!f || !f.group_curves) return {}
  const colors = ['#22c55e', '#3b82f6', '#94a3b8', '#fbbf24', '#ef4444']
  return {
    backgroundColor: 'transparent',
    title: { text: f.name + ' · 5分组', textStyle: { color: '#cbd5e1', fontSize: 13 } },
    legend: { textStyle: { color: '#cbd5e1' }, top: 24 },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 60, bottom: 30 },
    xAxis: { type: 'category', data: f.group_curves.dates, axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: '#475569' } } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: v => (v * 100).toFixed(0) + '%' }, splitLine: { lineStyle: { color: '#1e293b' } }, axisLine: { lineStyle: { color: '#475569' } } },
    series: f.group_curves.groups.map((g, i) => ({
      name: `第${i+1}组${i === 0 ? '(最低)' : i === 4 ? '(最高)' : ''}`,
      type: 'line', data: g, smooth: true, showSymbol: false,
      lineStyle: { color: colors[i], width: i === 0 || i === 4 ? 2.5 : 1.5 },
    })),
  }
})

const icSeriesOption = computed(() => {
  const f = bestFactor.value
  if (!f) return {}
  return {
    backgroundColor: 'transparent',
    title: { text: f.name + ` · IC=${f.ic_mean}, IR=${f.ir}`, textStyle: { color: '#cbd5e1', fontSize: 13 } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 50, bottom: 30 },
    xAxis: { type: 'category', data: f.ic_series.map(d => d.date), axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: '#475569' } } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } }, axisLine: { lineStyle: { color: '#475569' } } },
    series: [{ type: 'bar', data: f.ic_series.map(d => d.ic), itemStyle: { color: p => p.value >= 0 ? '#ef4444' : '#22c55e' } }],
  }
})

const heatmapOption = computed(() => {
  if (!result.value) return {}
  const h = result.value.ic.heatmap
  const data = []
  h.rows.forEach((r, i) => {
    r.values.forEach((v, j) => {
      if (v !== null) data.push([j, i, v])
    })
  })
  return {
    backgroundColor: 'transparent',
    tooltip: { position: 'top' },
    grid: { left: 100, right: 30, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: h.dates.map(d => d.slice(5)), axisLabel: { color: '#94a3b8', fontSize: 9 }, splitArea: { show: false } },
    yAxis: { type: 'category', data: h.rows.map(r => r.factor), axisLabel: { color: '#cbd5e1' } },
    visualMap: { min: -0.3, max: 0.3, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, textStyle: { color: '#cbd5e1' }, inRange: { color: ['#22c55e', '#0f172a', '#ef4444'] } },
    series: [{ type: 'heatmap', data, label: { show: false } }],
  }
})

const screeOption = computed(() => {
  if (!result.value) return {}
  const s = result.value.pca.scree
  return {
    backgroundColor: 'transparent',
    legend: { textStyle: { color: '#cbd5e1' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 50, top: 40, bottom: 30 },
    xAxis: { type: 'category', data: s.map(x => x.pc), axisLabel: { color: '#94a3b8' }, axisLine: { lineStyle: { color: '#475569' } } },
    yAxis: [
      { type: 'value', name: '特征根', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
      { type: 'value', name: '方差解释率', axisLabel: { color: '#94a3b8', formatter: v => (v*100).toFixed(0) + '%' }, splitLine: { show: false } },
    ],
    series: [
      { name: '特征根', type: 'bar', data: s.map(x => x.eigenvalue), itemStyle: { color: '#3b82f6' } },
      { name: '方差解释率', type: 'line', yAxisIndex: 1, data: s.map(x => x.explained), lineStyle: { color: '#fbbf24' }, itemStyle: { color: '#fbbf24' } },
    ],
  }
})

const loadingsOption = computed(() => {
  if (!result.value) return {}
  const lm = result.value.pca.loadings_matrix
  const comps = result.value.pca.components.map(c => c.name)
  const data = []
  lm.forEach((row, i) => {
    row.loadings.forEach((v, j) => data.push([j, i, v]))
  })
  return {
    backgroundColor: 'transparent',
    tooltip: { position: 'top' },
    grid: { left: 110, right: 30, top: 20, bottom: 50 },
    xAxis: { type: 'category', data: comps, axisLabel: { color: '#cbd5e1' } },
    yAxis: { type: 'category', data: lm.map(r => r.factor), axisLabel: { color: '#cbd5e1' } },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0, textStyle: { color: '#cbd5e1' }, inRange: { color: ['#22c55e', '#0f172a', '#ef4444'] } },
    series: [{ type: 'heatmap', data, label: { show: true, color: '#fff', fontSize: 10, formatter: p => p.value[2].toFixed(2) } }],
  }
})

onMounted(loadFactors)
</script>