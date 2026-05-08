import { createRouter, createWebHistory } from 'vue-router'

// 路由懒加载：每个页面打成独立 chunk，首屏只下载 Dashboard
const Dashboard = () => import('../views/Dashboard.vue')
const Stocks    = () => import('../views/Stocks.vue')
const Factor    = () => import('../views/Factor.vue')
const Backtest  = () => import('../views/Backtest.vue')
const Realtime  = () => import('../views/Realtime.vue')
const Sentiment = () => import('../views/Sentiment.vue')
const MLPredict = () => import('../views/MLPredict.vue')
const Login     = () => import('../views/auth/Login.vue')
const Register  = () => import('../views/auth/Register.vue')

const routes = [
  { path: '/login',    component: Login,    meta: { layout: 'auth', public: true } },
  { path: '/register', component: Register, meta: { layout: 'auth', public: true } },
  { path: '/',         component: Dashboard },
  { path: '/stocks',   component: Stocks },
  { path: '/factor',   component: Factor },
  { path: '/backtest', component: Backtest },
  { path: '/realtime', component: Realtime },
  { path: '/sentiment',component: Sentiment },
  { path: '/ml',       component: MLPredict },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.public && token && (to.path === '/login' || to.path === '/register')) {
    return { path: '/' }
  }
})

export default router
