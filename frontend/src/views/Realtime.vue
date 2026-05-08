<template>
  <div>
    <el-card style="background:#0f172a;border:1px solid #1e293b;color:#cbd5e1">
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span style="font-size:16px;font-weight:600;color:#fff">实时行情（iTick）</span>
        <el-input v-model="codeInput" placeholder="输入代码 600000 / 000001 / 300750" style="width:240px" />
        <el-select v-model="region" placeholder="自动" style="width:120px" clearable>
          <el-option label="自动" :value="null" />
          <el-option label="上海 SH" value="SH" />
          <el-option label="深圳 SZ" value="SZ" />
          <el-option label="香港 HK" value="HK" />
          <el-option label="美股 US" value="US" />
        </el-select>
        <el-button type="primary" :loading="loading" @click="load">查询</el-button>
        <el-tag v-if="lastUpdate" type="info">最近更新：{{ lastUpdate }}</el-tag>
      </div>
    </el-card>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="8">
        <el-card style="background:#0f172a;border:1px solid #1e293b;color:#cbd5e1">
          <template #header>
            <span style="color:#fff">实时报价</span>
          </template>
          <div v-if="quote">
            <div class="row"><span>代码</span><b>{{ quote.s }}</b></div>
            <div class="row"><span>最新价</span><b style="color:#22c55e">{{ quote.ld }}</b></div>
            <div class="row"><span>开盘</span><b>{{ quote.o }}</b></div>
            <div class="row"><span>最高</span><b style="color:#ef4444">{{ quote.h }}</b></div>
            <div class="row"><span>最低</span><b style="color:#22c55e">{{ quote.l }}</b></div>
            <div class="row"><span>成交量</span><b>{{ formatNum(quote.v) }}</b></div>
            <div class="row"><span>成交额</span><b>{{ formatNum(quote.tu) }}</b></div>
            <div class="row"><span>时间</span><b>{{ formatTs(quote.t) }}</b></div>
          </div>
          <el-empty v-else description="暂无数据" />
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card style="background:#0f172a;border:1px solid #1e293b">
          <template #header>
            <span style="color:#fff">日 K 线（最近 {{ klineData.length }} 根，按 iTick 数据；红涨绿跌）</span>
          </template>
          <v-chart v-if="klineData.length" :option="chartOption" style="height:400px" autoresize />
          <el-empty v-else description="暂无 K 线" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { CandlestickChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, DataZoomComponent } from 'echarts/components'
import api from '@/api'

use([CanvasRenderer, CandlestickChart, GridComponent, TooltipComponent, DataZoomComponent])

const route = useRoute()
const codeInput = ref(route.query.code ? String(route.query.code) : '600000')
const region = ref(null)
const loading = ref(false)
const quote = ref(null)
const klineData = ref([])
const lastUpdate = ref('')

function formatTs(ts) { return ts ? new Date(ts).toLocaleString() : '-' }
function formatNum(n) {
  if (n == null) return '-'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + ' 万'
  return n.toString()
}

async function load() {
  if (!codeInput.value.trim()) return ElMessage.warning('请输入代码')
  loading.value = true
  try {
    const [q, k] = await Promise.all([
      api.itickQuote(codeInput.value.trim(), region.value),
      api.itickKline(codeInput.value.trim(), 8, 60, region.value),
    ])
    quote.value = q.data.data
    klineData.value = (k.data.data || []).slice().sort((a, b) => a.t - b.t)
    lastUpdate.value = new Date().toLocaleTimeString()
    ElMessage.success('已更新')
  } catch (e) {
    const detail = e.response?.data?.detail || ''
    const status = e.response?.status
    if (status === 502 && /429|限流|配额/.test(detail)) {
      ElMessage.warning('iTick 已达 5次/分钟 配额，已自动等待重试；约 1 分钟后再点击查询即可恢复')
    } else {
      ElMessage.error(detail || '请求失败（检查 iTick token 与配额）')
    }
  } finally {
    loading.value = false
  }
}

const chartOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
  grid: { left: 50, right: 20, top: 20, bottom: 50 },
  xAxis: {
    type: 'category',
    data: klineData.value.map(d => new Date(d.t).toLocaleDateString()),
    axisLine: { lineStyle: { color: '#475569' } },
    axisLabel: { color: '#94a3b8' },
  },
  yAxis: {
    scale: true,
    axisLine: { lineStyle: { color: '#475569' } },
    axisLabel: { color: '#94a3b8' },
    splitLine: { lineStyle: { color: '#1e293b' } },
  },
  dataZoom: [{ type: 'inside' }, { type: 'slider', textStyle: { color: '#94a3b8' } }],
  series: [{
    type: 'candlestick',
    data: klineData.value.map(d => [d.o, d.c, d.l, d.h]),
    itemStyle: { color: '#ef4444', color0: '#22c55e', borderColor: '#ef4444', borderColor0: '#22c55e' },
  }],
}))

load()
</script>

<style scoped>
.row { display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px dashed #1e293b }
.row span { color:#94a3b8 }
.row b { color:#fff }
</style>
