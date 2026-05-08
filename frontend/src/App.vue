<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const isAuthLayout = computed(() => route.meta.layout === 'auth')

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <router-view v-if="isAuthLayout" />

  <el-container v-else style="height: 100vh;background:#0a101f">
    <el-aside width="220px" style="background:#0f172a;border-right:1px solid #1e293b">
      <div style="height:60px;line-height:60px;text-align:center;color:#409eff;font-size:20px;font-weight:bold;border-bottom:1px solid #1e293b">
        量化决策平台
      </div>
      <el-menu
        :default-active="route.path"
        background-color="#0f172a"
        text-color="#cbd5e1"
        active-text-color="#409eff"
        router
      >
        <el-menu-item index="/">数据大屏</el-menu-item>
        <el-menu-item index="/stocks">股票池</el-menu-item>
        <el-menu-item index="/factor">因子分析</el-menu-item>
        <el-menu-item index="/backtest">策略回测</el-menu-item>
        <el-menu-item index="/realtime">实时行情</el-menu-item>
        <el-menu-item index="/sentiment">舆情情感</el-menu-item>
        <el-menu-item index="/ml">AI 选股</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header style="background:#0f172a;border-bottom:1px solid #1e293b;color:#fff;display:flex;align-items:center;justify-content:space-between;padding:0 20px">
        <span style="font-size:18px;font-weight:500">FinQuantDash 全栈量化选股系统</span>
        <div v-if="auth.isLoggedIn" style="display:flex;align-items:center;gap:12px">
          <span style="color:#cbd5e1;font-size:14px">欢迎，{{ auth.name || auth.username }}</span>
          <el-button size="small" type="primary" plain @click="logout">退出</el-button>
        </div>
      </el-header>

      <el-main style="background:#0a101f;padding:20px">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
</style>  