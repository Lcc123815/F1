<template>
  <div class="auth-page">
    <AuthBackground />
    <nav class="main-nav">
      <div class="nav-container">
        <div class="nav-logo"><span class="logo-text">FinQuantDash</span></div>
        <div class="nav-actions">
          <button class="nav-login-btn" @click="$router.push('/register')">注册</button>
        </div>
      </div>
    </nav>

    <div class="login-container">
      <div class="left-section">
        <div class="brand">
          <h1 class="brand-logo">
            <span class="logo-part1">FinQuant</span><span class="logo-part2">Dash</span>
          </h1>
          <p class="brand-subtitle">FinQuantDash —— 你的智能量化投研伙伴</p>
        </div>
        <div class="brand-motto">
          <p>告别主观臆断，让数据驱动每一次投资决策。我们为专业投资者打造集数据回测、策略开发、实时交易于一体的高效、严谨的量化投研闭环。</p>
        </div>
        <p class="copyright">© 2026 FinQuantDash. All rights reserved.</p>
      </div>

      <div class="right-section">
        <div class="auth-card">
          <!-- 账号密码登录 -->
          <div v-if="panel === 'account'" class="auth-content">
            <div class="auth-header">
              <h2>用户登录</h2>
              <p>欢迎回来，请输入您的账号信息登录量化决策平台</p>
              <div class="divider" />
            </div>
            <form class="auth-form" @submit.prevent="onAccountLogin">
              <div class="form-group">
                <label>账号 / 手机号</label>
                <div class="input-wrapper">
                  <input v-model="account.username" type="text" placeholder="请输入账号或手机号" required />
                </div>
              </div>
              <div class="form-group">
                <label>登录密码</label>
                <div class="input-wrapper">
                  <input v-model="account.password" :type="showPwd ? 'text' : 'password'" placeholder="请输入登录密码" required />
                  <i class="fa-solid fa-eye" @click="showPwd = !showPwd" />
                </div>
              </div>
              <div class="form-options">
                <label class="checkbox-label">
                  <input v-model="account.remember" type="checkbox" />
                  <span class="checkmark" /><span>记住账号</span>
                </label>
                <a href="#" class="forgot-password" @click.prevent="panel = 'forgot'">忘记密码？</a>
              </div>
              <button type="submit" class="auth-btn" :disabled="loading">
                <span v-if="!loading">登录</span><span v-else>登录中...</span>
              </button>
              <div class="form-links">
                <a href="#" class="register-link" @click.prevent="$router.push('/register')">注册账户</a>
              </div>
            </form>
          </div>

          <!-- 找回密码（简化版：用户名 + 新密码） -->
          <div v-else-if="panel === 'forgot'" class="auth-content">
            <div class="auth-header">
              <h2>重置密码</h2>
              <p>请输入用户名并设置新密码</p>
              <div class="divider" />
            </div>
            <form class="auth-form" @submit.prevent="submitReset">
              <div class="form-group">
                <label>用户名</label>
                <div class="input-wrapper">
                  <input v-model="forgot.username" type="text" placeholder="请输入用户名" required />
                </div>
              </div>
              <div class="form-group">
                <label>新密码</label>
                <div class="input-wrapper">
                  <input v-model="forgot.password" type="password" placeholder="请设置新密码" required />
                </div>
              </div>
              <div class="form-group">
                <label>确认密码</label>
                <div class="input-wrapper">
                  <input v-model="forgot.confirm" type="password" placeholder="请再次输入密码" required />
                </div>
              </div>
              <button type="submit" class="auth-btn" :disabled="loading">
                {{ loading ? '提交中...' : '确认重置' }}
              </button>
              <div class="form-links">
                <a href="#" class="back-to-login" @click.prevent="panel = 'account'">返回登录</a>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import AuthBackground from '@/components/AuthBackground.vue'
import '@/assets/auth.css'

const router = useRouter()
const auth = useAuthStore()

const panel = ref('account')
const showPwd = ref(false)
const loading = ref(false)

const account = reactive({ username: '', password: '', remember: false })
const forgot = reactive({ username: '', password: '', confirm: '' })

async function onAccountLogin() {
  loading.value = true
  try {
    const { data } = await api.login({ username: account.username, password: account.password })
    auth.setSession(data.data)
    ElMessage.success(data.msg || '登录成功')
    router.push('/')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}

async function submitReset() {
  if (!forgot.username) return ElMessage.warning('请输入用户名')
  if (forgot.password !== forgot.confirm) return ElMessage.error('两次密码不一致')
  if (forgot.password.length < 6) return ElMessage.error('密码至少6位')
  loading.value = true
  try {
    await api.forgotPassword({ username: forgot.username, new_password: forgot.password })
    ElMessage.success('密码重置成功，请重新登录')
    panel.value = 'account'
    forgot.username = forgot.password = forgot.confirm = ''
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '重置失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; }
</style>
