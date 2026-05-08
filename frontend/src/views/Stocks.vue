<template>
  <el-card style="background:#0f172a;border:1px solid #1e293b">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
      <h3 style="color:#e2e8f0;margin:0">分类股票池</h3>
      <div style="display:flex;gap:8px;align-items:center">
        <el-input v-model="keyword" placeholder="搜索代码/名称/行业" style="width:220px" clearable @clear="onSearch" @keyup.enter="onSearch" />
        <el-button type="primary" :loading="loading" @click="onSearch">搜索</el-button>
        <el-button :loading="loading" @click="fetchData">刷新</el-button>
        <el-button type="success" @click="openAddDialog">+ 添加股票</el-button>
        <el-tooltip content="开启后每 30 秒自动拉取最新报价（命中后端 30s 缓存）">
          <el-switch v-model="autoRefresh" active-text="自动刷新" style="--el-switch-on-color:#22c55e" />
        </el-tooltip>
        <span v-if="lastUpdate" style="color:#94a3b8;font-size:12px">{{ lastUpdate }}</span>
      </div>
    </div>

    <el-tabs v-model="category" style="margin-top:12px" @tab-change="onTabChange">
      <el-tab-pane v-for="t in tabs" :key="t.value" :name="t.value">
        <template #label>
          <span :style="{ color: t.color }">{{ t.label }}</span>
          <el-badge :value="counts[t.value] || 0" :type="t.badge" style="margin-left:8px" />
        </template>
      </el-tab-pane>
    </el-tabs>

    <el-table
      :data="list"
      style="margin-top:16px"
      border
      :header-cell-style="{ background:'#1e293b', color:'#e2e8f0' }"
      :cell-style="{ background:'#0f172a', color:'#cbd5e1' }"
    >
      <el-table-column label="代码" prop="code" width="90" />
      <el-table-column label="名称" prop="name" width="120" />
      <el-table-column label="行业" prop="industry" width="120" />
      <el-table-column label="最新价" width="100" align="right">
        <template #default="{ row }">
          <span :style="{ color: priceColor(row), fontWeight: 600 }">{{ fmt(row.price) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="涨跌幅" width="100" align="right">
        <template #default="{ row }">
          <span :style="{ color: priceColor(row) }">{{ changePct(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="开盘" prop="open" width="80" align="right">
        <template #default="{ row }">{{ fmt(row.open) }}</template>
      </el-table-column>
      <el-table-column label="最高" width="80" align="right">
        <template #default="{ row }"><span style="color:#ef4444">{{ fmt(row.high) }}</span></template>
      </el-table-column>
      <el-table-column label="最低" width="80" align="right">
        <template #default="{ row }"><span style="color:#22c55e">{{ fmt(row.low) }}</span></template>
      </el-table-column>
      <el-table-column label="成交量" width="110" align="right">
        <template #default="{ row }">{{ fmtBig(row.volume) }}</template>
      </el-table-column>
      <el-table-column label="成交额" width="110" align="right">
        <template #default="{ row }">{{ fmtBig(row.turnover) }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="160" align="center">
        <template #default="{ row }">{{ fmtTs(row.ts) }}</template>
      </el-table-column>
      <el-table-column label="分类" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="categoryTag(row.category)" effect="dark">{{ categoryLabel(row.category) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="goRealtime(row)">K线</el-button>
          <el-dropdown trigger="click" @command="(c) => moveTo(row, c)">
            <el-button link type="warning">分类<el-icon class="el-icon--right"><arrow-down /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item v-for="t in tabs.filter(x => x.value !== 'all' && x.value !== row.category)"
                  :key="t.value" :command="t.value">移入{{ t.label }}</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-popconfirm title="确认从股票池移出？" @confirm="onRemove(row)">
            <template #reference>
              <el-button link type="danger">移出</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDialog" title="添加股票到池" width="420px">
      <el-form :model="newStock" label-width="80px">
        <el-form-item label="代码"><el-input v-model="newStock.code" placeholder="如 600519" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="newStock.name" placeholder="如 贵州茅台" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="newStock.industry" placeholder="如 白酒" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="newStock.category" style="width:100%">
            <el-option v-for="t in tabs.filter(x => x.value !== 'all')" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="newStock.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDialog = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="onAdd">添加</el-button>
      </template>
    </el-dialog>

    <el-pagination
      v-model:current-page="page"
      v-model:page-size="size"
      :total="total"
      :page-sizes="[10, 20, 30, 50, 100]"
      layout="total, sizes, prev, pager, next, jumper"
      style="margin-top:16px; text-align:right; color:#cbd5e1"
      background
      @size-change="fetchData"
      @current-change="fetchData"
    />
  </el-card>
</template>

<script setup>
import { onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import api from '@/api'

const router = useRouter()
const page = ref(1)
const size = ref(20)
const total = ref(0)
const list = ref([])
const keyword = ref('')
const loading = ref(false)
const autoRefresh = ref(false)
const lastUpdate = ref('')
const category = ref('all')
const counts = ref({})
const addDialog = ref(false)
const adding = ref(false)
const newStock = reactive({ code: '', name: '', industry: '', category: 'general', note: '' })
let timer = null

const tabs = [
  { label: '全部', value: 'all', color: '#cbd5e1', badge: 'info' },
  { label: '核心池', value: 'core', color: '#22c55e', badge: 'success' },
  { label: '普通池', value: 'general', color: '#3b82f6', badge: 'primary' },
  { label: '禁买池', value: 'blacklist', color: '#ef4444', badge: 'danger' },
]
function categoryLabel(v) { return ({ core: '核心', general: '普通', blacklist: '禁买' })[v] || v }
function categoryTag(v) { return ({ core: 'success', general: 'primary', blacklist: 'danger' })[v] || 'info' }

function fmt(n) { return n == null ? '-' : (+n).toFixed(2) }
function fmtBig(n) {
  if (n == null) return '-'
  if (n >= 1e8) return (n / 1e8).toFixed(2) + ' 亿'
  if (n >= 1e4) return (n / 1e4).toFixed(2) + ' 万'
  return (+n).toFixed(0)
}
function fmtTs(ts) { return ts ? new Date(ts).toLocaleString() : '-' }
function changePct(row) {
  if (row.price == null || !row.open) return '-'
  const pct = ((row.price - row.open) / row.open) * 100
  return (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%'
}
function priceColor(row) {
  if (row.price == null || !row.open) return '#cbd5e1'
  return row.price >= row.open ? '#ef4444' : '#22c55e'
}

async function fetchData() {
  loading.value = true
  try {
    const res = await api.poolList({
      page: page.value, size: size.value, keyword: keyword.value, category: category.value,
    })
    total.value = res.data.data.total
    list.value = res.data.data.list
    counts.value = res.data.data.counts || {}
    lastUpdate.value = '更新于 ' + new Date().toLocaleTimeString()
  } catch (err) {
    ElMessage.error('请求失败：' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

function onSearch() { page.value = 1; fetchData() }
function onTabChange() { page.value = 1; fetchData() }
function goRealtime(row) { router.push({ path: '/realtime', query: { code: row.code } }) }

async function moveTo(row, target) {
  try {
    await api.poolUpdateCategory(row.id, target)
    ElMessage.success(`已移入${categoryLabel(target)}池`)
    fetchData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

async function onRemove(row) {
  try {
    await api.poolRemove(row.id)
    ElMessage.success('已移出股票池')
    fetchData()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '操作失败') }
}

function openAddDialog() {
  console.log('[Stocks] open add dialog')
  Object.assign(newStock, { code: '', name: '', industry: '', category: 'general', note: '' })
  addDialog.value = true
}

async function onAdd() {
  if (!newStock.code || !newStock.name) return ElMessage.warning('代码和名称必填')
  adding.value = true
  try {
    await api.poolAdd({ ...newStock })
    ElMessage.success('已添加')
    addDialog.value = false
    Object.assign(newStock, { code: '', name: '', industry: '', category: 'general', note: '' })
    fetchData()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  } finally {
    adding.value = false
  }
}

function setupTimer() {
  if (timer) { clearInterval(timer); timer = null }
  if (autoRefresh.value) timer = setInterval(fetchData, 30000)
}

onMounted(() => {
  fetchData()
  setupTimer()
})
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

watch(autoRefresh, setupTimer)
</script>