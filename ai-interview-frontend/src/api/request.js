import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import router from '../router'

const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const timeout = Number(import.meta.env.VITE_API_TIMEOUT || 60000)

const api = axios.create({
  baseURL,
  timeout
})

// 请求拦截器：自动带上 token
api.interceptors.request.use(config => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

// 响应拦截器：统一处理错误
api.interceptors.response.use(
  response => {
    const data = response.data
    if (data.code === 200) {
      return data.data
    }
    return Promise.reject(new Error(data.message || '请求失败'))
  },
  error => {
    if (error.response?.status === 403 || error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
    }

    const data = error.response?.data
    let msg = data?.message || error.message || '网络错误'

    if (!error.response && error.message === 'Network Error') {
      msg = '网络连接失败，请稍后重试；如果反复失败，请检查服务状态或简历文件大小'
    } else if (error.response?.status === 502) {
      msg = '服务暂时不可用，请稍后重试'
    } else if (error.response?.status === 413) {
      msg = '上传文件过大，请控制在 10MB 以内'
    }

    if (data?.detail) {
      if (Array.isArray(data.detail)) {
        msg = data.detail.map(d => d.msg || d.message || JSON.stringify(d)).join('; ')
      } else if (typeof data.detail === 'string') {
        msg = data.detail
      }
    }

    return Promise.reject(new Error(msg))
  }
)

export default api
