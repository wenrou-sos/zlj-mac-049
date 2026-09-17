import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/', timeout: 20000 })

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
    return Promise.reject(err)
  }
)

export default http

export const dashboardApi = {
  get: () => http.get('/api/dashboard').then((r) => r.data),
}

export const collectionApi = {
  list: (params) => http.get('/api/collections', { params }).then((r) => r.data),
  meta: () => http.get('/api/collections/meta').then((r) => r.data),
  get: (id) => http.get(`/api/collections/${id}`).then((r) => r.data),
  create: (data) => http.post('/api/collections', data).then((r) => r.data),
  update: (id, data) => http.put(`/api/collections/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/api/collections/${id}`).then((r) => r.data),
  move: (id, data) =>
    http.post(`/api/collections/${id}/movements`, data).then((r) => r.data),
}

export const movementApi = {
  list: (params) => http.get('/api/movements', { params }).then((r) => r.data),
}

export const locationApi = {
  list: (params) => http.get('/api/locations', { params }).then((r) => r.data),
  create: (data) => http.post('/api/locations', data).then((r) => r.data),
  update: (id, data) => http.put(`/api/locations/${id}`, data).then((r) => r.data),
  remove: (id) => http.delete(`/api/locations/${id}`).then((r) => r.data),
  addReading: (id, data) =>
    http.post(`/api/locations/${id}/readings`, data).then((r) => r.data),
}

export const exhibitionApi = {
  list: (params) => http.get('/api/exhibitions', { params }).then((r) => r.data),
  get: (id) => http.get(`/api/exhibitions/${id}`).then((r) => r.data),
  create: (data) => http.post('/api/exhibitions', data).then((r) => r.data),
  addItem: (id, data) =>
    http.post(`/api/exhibitions/${id}/items`, data).then((r) => r.data),
  dismount: (id, itemId, return_location_id) =>
    http
      .delete(`/api/exhibitions/${id}/items/${itemId}`, {
        params: return_location_id ? { return_location_id } : {},
      })
      .then((r) => r.data),
}

export const restorationApi = {
  list: (params) => http.get('/api/restorations', { params }).then((r) => r.data),
  create: (data) => http.post('/api/restorations', data).then((r) => r.data),
  addTimeline: (id, data) =>
    http.post(`/api/restorations/${id}/timeline`, data).then((r) => r.data),
  complete: (id, data, return_location_id) =>
    http
      .post(`/api/restorations/${id}/complete`, data, {
        params: return_location_id ? { return_location_id } : {},
      })
      .then((r) => r.data),
}

export const loanApi = {
  list: (params) => http.get('/api/loans', { params }).then((r) => r.data),
  create: (data) => http.post('/api/loans', data).then((r) => r.data),
  return: (id, data) => http.post(`/api/loans/${id}/return`, data).then((r) => r.data),
}

export const envApi = {
  readings: (location_id, hours = 72) =>
    http.get('/api/environment/readings', { params: { location_id, hours } }).then((r) => r.data),
  alerts: (params) => http.get('/api/environment/alerts', { params }).then((r) => r.data),
  ack: (id, by = '管理员') =>
    http.post(`/api/environment/alerts/${id}/ack`, null, { params: { by } }).then((r) => r.data),
  simulate: (data) => http.post('/api/environment/simulate', data).then((r) => r.data),
}

export const inventoryApi = {
  tasks: (params) => http.get('/api/inventory/tasks', { params }).then((r) => r.data),
  createTask: (data) => http.post('/api/inventory/tasks', data).then((r) => r.data),
  getTask: (id) => http.get(`/api/inventory/tasks/${id}`).then((r) => r.data),
  cancelTask: (id) => http.post(`/api/inventory/tasks/${id}/cancel`).then((r) => r.data),
  closeTask: (id, data) => http.post(`/api/inventory/tasks/${id}/close`, data).then((r) => r.data),
  scan: (id, data) => http.post(`/api/inventory/tasks/${id}/scan`, data).then((r) => r.data),
  checkItem: (itemId, data) =>
    http.post(`/api/inventory/items/${itemId}/check`, data).then((r) => r.data),
  reviewItem: (itemId, data) =>
    http.post(`/api/inventory/items/${itemId}/review`, data).then((r) => r.data),
  createAdjustment: (itemId, data) =>
    http.post(`/api/inventory/items/${itemId}/adjustments`, data).then((r) => r.data),
  approveAdjustment: (id, data) =>
    http.post(`/api/inventory/adjustments/${id}/approve`, data).then((r) => r.data),
  rejectAdjustment: (id, data) =>
    http.post(`/api/inventory/adjustments/${id}/reject`, data).then((r) => r.data),
}
