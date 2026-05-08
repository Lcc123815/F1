<template>
  <div class="background">
    <div class="gradient-overlay" />
    <div class="grid-container" />
    <canvas ref="particlesRef" id="particles" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const particlesRef = ref(null)
let raf = 0
let resizeHandler = null

onMounted(() => {
  const canvas = particlesRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const dpr = window.devicePixelRatio || 1

  const resize = () => {
    canvas.width = window.innerWidth * dpr
    canvas.height = window.innerHeight * dpr
    canvas.style.width = window.innerWidth + 'px'
    canvas.style.height = window.innerHeight + 'px'
    ctx.scale(dpr, dpr)
  }
  resize()
  resizeHandler = resize
  window.addEventListener('resize', resize)

  const particles = Array.from({ length: 60 }).map(() => ({
    x: Math.random() * window.innerWidth,
    y: Math.random() * window.innerHeight,
    vx: (Math.random() - 0.5) * 0.4,
    vy: (Math.random() - 0.5) * 0.4,
    r: Math.random() * 1.6 + 0.4,
    a: Math.random() * 0.5 + 0.2,
  }))

  const tick = () => {
    ctx.clearRect(0, 0, window.innerWidth, window.innerHeight)
    for (const p of particles) {
      p.x += p.vx
      p.y += p.vy
      if (p.x < 0 || p.x > window.innerWidth) p.vx *= -1
      if (p.y < 0 || p.y > window.innerHeight) p.vy *= -1
      ctx.beginPath()
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
      ctx.fillStyle = `rgba(0, 212, 255, ${p.a})`
      ctx.fill()
    }
    // connecting lines
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j]
        const dx = a.x - b.x, dy = a.y - b.y
        const d = Math.sqrt(dx * dx + dy * dy)
        if (d < 120) {
          ctx.strokeStyle = `rgba(0, 212, 255, ${0.12 * (1 - d / 120)})`
          ctx.lineWidth = 1
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(b.x, b.y)
          ctx.stroke()
        }
      }
    }
    raf = requestAnimationFrame(tick)
  }
  tick()
})

onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
})
</script>
