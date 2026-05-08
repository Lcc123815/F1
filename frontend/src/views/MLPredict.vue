<template>
  <div>
    <!-- 控制面板 -->
    <el-card style="background:#0f172a;border:1px solid #1e293b">
      <h3 style="color:#e2e8f0;margin:0 0 12px 0">机器学习多因子合成（LightGBM + SHAP）</h3>
      <el-form :model="form" inline label-position="top">
        <el-form-item label="股票池">
          <el-select v-model="form.use_pool" style="width:120px">
            <el-option label="核心池" value="core" />
            <el-option label="普通池" value="general" />
            <el-option label="全部" value="all" />
          </el-select>
        </el-form-item>
        <el-form-item label="股票数">
          <el-input-number v-model="form.max_codes" :min="5" :max="60" style="width:110px" />
        </el-form-item>
        <el-form-item label="预测周期(日)">
          <el-input-number v-model="form.horizon" :min="1" :max="20" style="width:110px" />
        </el-form-item>
        <el-form-item label="K线根数">
          <el-input-number v-model="form.limit" :min="120" :max="500" :step="50" style="width:110px" />
        </el-form-item>
        <el-form-item label="树个数">
          <el-input-number v-model="form.n_estimators" :min="50" :max="500" :step="50" style="width:110px" />
        </el-form-item>
        <el-form-item label="学习率">
          <el-input-number v-model="form.learning_rate" :min="0.01" :max="0.3" :step="0.01" :precision="2" style="width:110px" />
        </el-form-item>
        <el-form-item label="树深度">
          <el-input-number v-model="form.max_depth" :min="3" :max="10" style="width:90px" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="training" @click="onTrain">训练模型</el-button>
          <el-button type="success" :loading="predicting" :disabled="!status.trained" @click="onPredict">预测排行</el-button>
        </el-form-item>
      </el-form>
      <div style="color:#94a3b8;font-size:12px">
        <span v-if="status.trained">
          ✅ 模型已就绪 · trained_at: {{ status.trained_at }} · 因子数: {{ status.feature_keys?.length }}
          · 训练 IC: <b style="color:#22c55e">{{ status.metrics?.ic_train }}</b>
          · 测试 IC: <b style="color:#fbbf24">{{ status.metrics?.ic_test }}</b>
        </span>
        <span v-else>⚠️ 尚未训练，请先点"训练模型"</span>
      </div>
    </el-card>

    <!-- 训练结果 -->
    <el-row v-if="trainResult" :gutter="12" style="margin-top:12px">
      <el-col :span="8">
        <el-card style="background:#0f172a;border:1px solid #1e293b;height:100%">
          <template #header><span style="color:#fff">训练评估</span></template>
          <div class="kv"><span>训练集 IC</span><b :class="trainResult.metrics.ic_train > 0.1 ? 'good' : 'mid'">{{ trainResult.metrics.ic_train }}</b></div>
          <div class="kv"><span>测试集 IC</span><b :class="trainResult.metrics.ic_test > 0.05 ? 'good' : trainResult.metrics.ic_test > 0 ? 'mid' : 'bad'">{{ trainResult.metrics.ic_test }}</b></div>
          <div class="kv"><span>训练样本</span><b>{{ trainResult.metrics.n_train }} ({{ trainResult.metrics.n_dates_train }} 天)</b></div>
          <div class="kv"><span>测试样本</span><b>{{ trainResult.metrics.n_test }} ({{ trainResult.metrics.n_dates_test }} 天)</b></div>
          <div class="kv"><span>RMSE 训练</span><b>{{ trainResult.metrics.rmse_train }}</b></div>
          <div class="kv"><span>RMSE 测试</span><b>{{ trainResult.metrics.rmse_test }}</b></div>
          <div class="kv"><span>最佳迭代</span><b>{{ trainResult.metrics.best_iteration }}</b></div>
          <div class="kv"><span>训练耗时</span><b>{{ trainResult.metrics.elapsed }} s</b></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card style="background:#0f172a;border:1px solid #1e293b;height:100%">
          <template #header><span style="color:#fff">特征重要性（gain）</span></template>
          <v-chart :option="importanceOption" style="height:260px" autoresize />
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card style="background:#0f172a;border:1px solid #1e293b;height:100%">
          <template #header><span style="color:#fff">测试集 IC 时序</span></template>
          <v-chart :option="icSeriesOption" style="height:260px" autoresize />
        </el-card>
      </el-col>
    </el-row>

    <el-card v-if="trainResult" style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
      <template #header><span style="color:#fff">分组累积收益（按预测值 5 分组，q1=最低，q5=最高）</span></template>
      <v-chart :option="groupCurveOption" style="height:320px" autoresize />
    </el-card>

    <!-- 预测排行榜 -->
    <el-card v-if="predictResult" style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
      <template #header>
        <span style="color:#fff">📈 今日预测排行榜（未来 {{ predictResult.horizon }} 日预期收益）</span>
        <span style="color:#94a3b8;margin-left:12px;font-size:12px">点击行展开 SHAP 解释</span>
      </template>
      <el-table :data="predictResult.ranking" border row-key="code" stripe
        :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div v-if="row.explanation" style="padding:12px 24px;background:#0b1220">
              <div style="margin-bottom:8px;color:#94a3b8;font-size:13px">
                基准值（全局均值预测）：<b style="color:#cbd5e1">{{ row.explanation.base_value }}</b>
                <span style="margin:0 6px">+</span> 各因子贡献 = 预测值 <b style="color:#fbbf24">{{ row.explanation.predicted }}</b>
              </div>
              <v-chart :option="shapOption(row.explanation)" style="height:240px" autoresize />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="排名" prop="rank" width="70" align="center" />
        <el-table-column label="代码" prop="code" width="100" />
        <el-table-column label="预测收益" align="right" width="130">
          <template #default="{ row }">
            <span :style="{ color: row.predicted_return > 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }">
              {{ (row.predicted_return * 100).toFixed(2) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="数据日期" prop="last_date" width="120" />
        <el-table-column v-for="fk in predictResult.feature_keys" :key="fk" :label="zhName(fk)" align="right">
          <template #default="{ row }">{{ Number(row[fk]).toFixed(4) }}</template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import api from '@/api'

use([CanvasRenderer, BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const form = reactive({
  use_pool: 'core',
  max_codes: 12,
  horizon: 5,
  limit: 250,
  n_estimators: 200,
  learning_rate: 0.05,
  max_depth: 5,
})

// 因子中文名映射（后端仍用英文 key，前端展示用中文）
const factorNameMap = ref({})
const zhName = (key) => factorNameMap.value[key] || key

async function loadFactorMeta() {
  try {
    const { data } = await api.factorList()
    const m = {}
    for (const f of (data.data || [])) m[f.key] = f.name
    factorNameMap.value = m
  } catch {}
}

const training = ref(false)
const predicting = ref(false)
const trainResult = ref(null)
const predictResult = ref(null)
const status = ref({ trained: false })

async function loadStatus() {
  try {
    const { data } = await api.mlStatus()
    status.value = data.data || { trained: false }
  } catch {}
}

async function onTrain() {
  training.value = true
  try {
    const { data } = await api.mlTrain({ ...form })
    trainResult.value = data.data
    status.value = { trained: true, ...data.data }
    ElMessage.success(`训练完成 · 测试 IC=${data.data.metrics.ic_test} · 耗时 ${data.data.metrics.elapsed}s`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '训练失败')
  } finally {
    training.value = false
  }
}

async function onPredict() {
  predicting.value = true
  try {
    const { data } = await api.mlPredict({
      use_pool: form.use_pool,
      max_codes: Math.max(form.max_codes, 30),
      top_n: 15,
      explain: true,
    })
    predictResult.value = data.data
    ElMessage.success(`预测完成（共 ${data.data.all_count} 只候选，展示前 15）`)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '预测失败')
  } finally {
    predicting.value = false
  }
}

const importanceOption = computed(() => {
  if (!trainResult.value) return {}
  const items = [...trainResult.value.importance].reverse()
  return {
    backgroundColor: 'transparent',
    grid: { left: 110, right: 50, top: 10, bottom: 30 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
    yAxis: { type: 'category', data: items.map(i => zhName(i.feature)), axisLabel: { color: '#cbd5e1' } },
    series: [{ type: 'bar', data: items.map(i => i.gain), itemStyle: { color: '#3b82f6' }, label: { show: true, color: '#fff', position: 'right', formatter: v => v.value.toFixed(0) } }],
  }
})

const icSeriesOption = computed(() => {
  if (!trainResult.value) return {}
  const ic = trainResult.value.ic_series
  return {
    backgroundColor: 'transparent',
    grid: { left: 50, right: 20, top: 10, bottom: 50 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ic.map(d => d.date), axisLabel: { color: '#94a3b8', fontSize: 10 } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
    dataZoom: [{ type: 'inside' }, { type: 'slider', textStyle: { color: '#94a3b8' } }],
    series: [{ type: 'bar', data: ic.map(d => d.ic), itemStyle: { color: p => p.value >= 0 ? '#ef4444' : '#22c55e' } }],
  }
})

const groupCurveOption = computed(() => {
  if (!trainResult.value) return {}
  const c = trainResult.value.group_curve
  const colors = ['#22c55e', '#3b82f6', '#94a3b8', '#fbbf24', '#ef4444']
  return {
    backgroundColor: 'transparent',
    legend: { textStyle: { color: '#cbd5e1' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 30, bottom: 30 },
    xAxis: { type: 'category', data: c.dates, axisLabel: { color: '#94a3b8' } },
    yAxis: { type: 'value', axisLabel: { color: '#94a3b8', formatter: v => (v * 100).toFixed(1) + '%' }, splitLine: { lineStyle: { color: '#1e293b' } } },
    series: Object.entries(c.groups).map(([k, vals], i) => ({
      name: `${k}${i === 0 ? '(最低)' : i === 4 ? '(最高)' : ''}`,
      type: 'line', data: vals, smooth: true, showSymbol: false,
      lineStyle: { color: colors[i], width: i === 0 || i === 4 ? 2.5 : 1.5 },
    })),
  }
})

function shapOption(exp) {
  const items = [...exp.contributions].reverse()
  const zhItems = items.map(i => ({ ...i, zh: zhName(i.feature) }))
  return {
    backgroundColor: 'transparent',
    grid: { left: 120, right: 60, top: 10, bottom: 30 },
    tooltip: {
      trigger: 'item',
      formatter: (p) => {
        const it = zhItems.find(x => x.zh === p.name)
        return `${p.name}<br/>SHAP 贡献: ${p.value > 0 ? '+' : ''}${p.value.toFixed(4)}<br/>原始值: ${it ? it.value.toFixed(4) : '-'}`
      },
    },
    xAxis: { type: 'value', axisLabel: { color: '#94a3b8' }, splitLine: { lineStyle: { color: '#1e293b' } } },
    yAxis: { type: 'category', data: zhItems.map(i => i.zh), axisLabel: { color: '#cbd5e1' } },
    series: [{
      type: 'bar', data: zhItems.map(i => ({ value: i.shap, itemStyle: { color: i.shap >= 0 ? '#ef4444' : '#22c55e' } })),
      label: { show: true, color: '#fff', position: 'right', formatter: p => (p.value > 0 ? '+' : '') + p.value.toFixed(4) },
    }],
  }
}

onMounted(() => { loadStatus(); loadFactorMeta() })
</script>

<style scoped>
.kv { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px dashed #1e293b }
.kv span { color:#94a3b8 }
.kv b { color:#fff }
.good { color:#22c55e !important }
.mid  { color:#fbbf24 !important }
.bad  { color:#ef4444 !important }
:deep(.el-table) { --el-table-bg-color:#0f172a; --el-table-tr-bg-color:#0f172a; --el-table-row-hover-bg-color:#1e293b; --el-table-border-color:#1e293b; --el-fill-color-lighter:#131c30; --el-fill-color-light:#131c30; color:#cbd5e1 }
:deep(.el-table--striped .el-table__body tr.el-table__row--striped td.el-table__cell) { background-color:#131c30 !important }
:deep(.el-form-item__label) { color:#cbd5e1 }
</style>
