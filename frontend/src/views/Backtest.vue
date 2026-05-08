<template>
  <div>
    <!-- 配置面板 -->
    <el-card style="background:#0f172a;border:1px solid #1e293b">
      <h3 style="color:#e2e8f0;margin:0 0 12px 0">策略回测</h3>
      <el-form :model="form" inline label-width="80px" label-position="top">
        <el-form-item label="股票代码">
          <el-input v-model="form.code" placeholder="如 600000" style="width:140px" />
        </el-form-item>
        <el-form-item label="策略">
          <el-select v-model="form.strategy" style="width:180px" @change="onStrategyChange">
            <el-option v-for="s in strategies" :key="s.key" :label="s.name" :value="s.key">
              <span>{{ s.name }}</span>
              <span style="color:#94a3b8;font-size:12px;margin-left:8px">{{ s.description }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item v-for="(_, k) in form.params" :key="k" :label="k">
          <el-input-number v-model="form.params[k]" :min="0" :step="k.includes('std') ? 0.1 : 1" style="width:120px" />
        </el-form-item>
        <el-form-item label="回测 K 线数">
          <el-input-number v-model="form.limit" :min="60" :max="1000" :step="50" style="width:130px" />
        </el-form-item>
        <el-form-item label="初始资金">
          <el-input-number v-model="form.initial_cash" :min="10000" :step="10000" style="width:140px" />
        </el-form-item>
        <el-form-item label="手续费">
          <el-input-number v-model="form.fee" :min="0" :max="0.01" :step="0.0001" :precision="4" style="width:130px" />
        </el-form-item>
        <el-form-item label=" ">
          <el-button type="primary" :loading="running" @click="onRun">运行回测</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 指标卡 -->
    <el-row v-if="result" :gutter="12" style="margin-top:12px">
      <el-col :span="4" v-for="m in metricCards" :key="m.label">
        <el-card style="background:#0f172a;border:1px solid #1e293b;text-align:center">
          <div style="color:#94a3b8;font-size:12px">{{ m.label }}</div>
          <div :style="{ color: m.color, fontSize:'22px', fontWeight:600, marginTop:'6px' }">{{ m.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 净值曲线 -->
    <el-card v-if="result" style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
      <template #header><span style="color:#fff">净值曲线（策略 vs 基准买入持有）</span></template>
      <v-chart :option="curveOption" style="height:380px" autoresize />
    </el-card>

    <!-- 交易记录 -->
    <el-card v-if="result" style="background:#0f172a;border:1px solid #1e293b;margin-top:12px">
      <template #header>
        <span style="color:#fff">交易记录（共 {{ result.trades.length }} 笔，胜率 {{ (result.metrics.win_rate*100).toFixed(1) }}%）</span>
      </template>
      <el-table :data="result.trades" border
        :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }"
        :cell-style="{ background:'#0f172a', color:'#cbd5e1' }">
        <el-table-column label="开仓日期" prop="open_date" />
        <el-table-column label="平仓日期" prop="close_date" />
        <el-table-column label="开仓价" prop="open_price" align="right" />
        <el-table-column label="平仓价" prop="close_price" align="right" />
        <el-table-column label="持仓天数" prop="hold_days" align="right" />
        <el-table-column label="收益率(%)" align="right">
          <template #default="{ row }">
            <span :style="{ color: row.pnl >= 0 ? '#ef4444' : '#22c55e', fontWeight: 600 }">
              {{ row.pnl >= 0 ? '+' : '' }}{{ row.pnl }}%
            </span>
          </template>
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
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, DataZoomComponent } from 'echarts/components'
import api from '@/api'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent, DataZoomComponent])

const strategies = ref([])
const form = reactive({
  code: '600000',
  strategy: 'sma_cross',
  params: { fast: 5, slow: 20 },
  limit: 250,
  initial_cash: 100000,
  fee: 0.0003,
})
const running = ref(false)
const result = ref(null)

function onStrategyChange(key) {
  const s = strategies.value.find(x => x.key === key)
  if (s) form.params = { ...s.params }
}

async function loadStrategies() {
  try {
    const { data } = await api.listStrategies()
    strategies.value = data.data
  } catch (e) {
    ElMessage.error('加载策略列表失败')
  }
}

async function onRun() {
  if (!form.code) return ElMessage.warning('请输入股票代码')
  running.value = true
  try {
    const { data } = await api.runBacktest({
      code: form.code,
      strategy: form.strategy,
      params: form.params,
      initial_cash: form.initial_cash,
      fee: form.fee,
      limit: form.limit,
    })
    result.value = data.data
    ElMessage.success('回测完成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '回测失败')
  } finally {
    running.value = false
  }
}

const metricCards = computed(() => {
  if (!result.value) return []
  const m = result.value.metrics
  const pct = v => (v * 100).toFixed(2) + '%'
  return [
    { label: '总收益', value: pct(m.total_return), color: m.total_return >= 0 ? '#ef4444' : '#22c55e' },
    { label: '年化收益', value: pct(m.annual_return), color: m.annual_return >= 0 ? '#ef4444' : '#22c55e' },
    { label: '最大回撤', value: pct(m.max_drawdown), color: '#22c55e' },
    { label: '夏普比率', value: m.sharpe.toFixed(2), color: m.sharpe >= 1 ? '#ef4444' : '#cbd5e1' },
    { label: '胜率', value: pct(m.win_rate), color: '#3b82f6' },
    { label: '交易次数', value: m.trades, color: '#cbd5e1' },
  ]
})

const curveOption = computed(() => {
  if (!result.value) return {}
  const c = result.value.curve
  return {
    backgroundColor: 'transparent',
    legend: { textStyle: { color: '#cbd5e1' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 30, top: 40, bottom: 60 },
    xAxis: {
      type: 'category', data: c.dates,
      axisLine: { lineStyle: { color: '#475569' } },
      axisLabel: { color: '#94a3b8' },
    },
    yAxis: {
      type: 'value', scale: true,
      axisLine: { lineStyle: { color: '#475569' } },
      axisLabel: { color: '#94a3b8' },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    dataZoom: [{ type: 'inside' }, { type: 'slider', textStyle: { color: '#94a3b8' } }],
    series: [
      { name: '策略净值', type: 'line', data: c.equity, smooth: true, lineStyle: { color: '#22c55e', width: 2 }, showSymbol: false },
      { name: '基准（买入持有）', type: 'line', data: c.benchmark, smooth: true, lineStyle: { color: '#94a3b8', width: 1, type: 'dashed' }, showSymbol: false },
    ],
  }
})

onMounted(loadStrategies)
</script>