<template>
  <div class="auth-page">
    <AuthBackground />
    <div class="register-container">
      <div class="left-section">
        <div class="brand">
          <h1 class="brand-logo">
            <span class="logo-part1">FinQuant</span><span class="logo-part2">Dash</span>
          </h1>
          <p class="brand-subtitle">全栈量化选股系统 | 专业量化决策平台</p>
        </div>
        <div class="brand-motto">
          <p>以数据驱动决策，用算法捕捉市场机会，为专业投资者打造高效、严谨的量化投研工具。</p>
        </div>
        <p class="copyright">© 2026 FinQuantDash All Rights Reserved</p>
      </div>

      <div class="right-section">
        <div class="register-card">
          <div class="register-header">
            <h2>用户注册</h2>
            <p>创建您的量化决策平台账号</p>
            <div class="divider" />
          </div>

          <form class="register-form" @submit.prevent="onSubmit">
            <div class="form-group" :class="{ error: errors.username }">
              <label>用户名</label>
              <div class="input-wrapper">
                <input v-model="form.username" type="text" placeholder="请输入用户名" required />
              </div>
              <span class="error-message" :class="{ show: !!errors.username }">{{ errors.username }}</span>
            </div>

            <div class="form-group" :class="{ error: errors.phone }">
              <label>手机号码（可选）</label>
              <div class="input-wrapper">
                <input v-model="form.phone" type="tel" placeholder="请输入手机号码（可选）" />
              </div>
              <span class="error-message" :class="{ show: !!errors.phone }">{{ errors.phone }}</span>
            </div>

            <div class="form-group" :class="{ error: errors.password }">
              <label>登录密码</label>
              <div class="input-wrapper">
                <input v-model="form.password" :type="showPwd ? 'text' : 'password'" placeholder="请输入登录密码" required />
                <i class="fa-regular fa-eye" @click="showPwd = !showPwd" />
              </div>
              <span class="password-hint">密码需包含字母、数字，长度6-20位</span>
              <span class="error-message" :class="{ show: !!errors.password }">{{ errors.password }}</span>
            </div>

            <div class="form-group" :class="{ error: errors.confirm }">
              <label>确认密码</label>
              <div class="input-wrapper">
                <input v-model="form.confirm" type="password" placeholder="请再次输入密码" required />
              </div>
              <span class="error-message" :class="{ show: !!errors.confirm }">{{ errors.confirm }}</span>
            </div>

            <div class="form-options">
              <label class="checkbox-label">
                <input v-model="form.agree" type="checkbox" required />
                <span class="checkmark" />
                <span>我已阅读并同意<a href="#" class="terms-link">《用户协议》</a>和<a href="#" class="terms-link">《隐私政策》</a></span>
              </label>
            </div>

            <button type="submit" class="register-btn" :disabled="submitting">
              {{ submitting ? '注册中...' : '注册' }}
            </button>
          </form>

          <p class="login-link">已有账号？<a href="#" @click.prevent="$router.push('/login')">立即登录</a></p>
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
import AuthBackground from '@/components/AuthBackground.vue'
import '@/assets/auth.css'

const router = useRouter()

const form = reactive({ username: '', phone: '', password: '', confirm: '', agree: false })
const errors = reactive({ username: '', phone: '', password: '', confirm: '' })

const showPwd = ref(false)
const submitting = ref(false)

const phoneRe = /^1[3-9]\d{9}$/
const pwdRe = /^(?=.*[A-Za-z])(?=.*\d).{6,20}$/

function validate() {
  errors.username = form.username.length >= 2 ? '' : '用户名至少2位'
  errors.phone = !form.phone || phoneRe.test(form.phone) ? '' : '手机号格式不正确'
  errors.password = pwdRe.test(form.password) ? '' : '密码需包含字母和数字，6-20位'
  errors.confirm = form.confirm === form.password ? '' : '两次密码不一致'
  return !Object.values(errors).some(Boolean)
}

async function onSubmit() {
  if (!form.agree) return ElMessage.warning('请先同意用户协议')
  if (!validate()) return
  submitting.value = true
  try {
    await api.register({
      username: form.username,
      phone: form.phone || null,
      password: form.password,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.auth-page { min-height: 100vh; }
</style>
