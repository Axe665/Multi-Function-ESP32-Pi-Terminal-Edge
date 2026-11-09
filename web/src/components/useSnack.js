import { ref } from 'vue'

// 一个全局 snackbar 就够，页面之间不抢
const text = ref('')
let timer = 0

export function useSnack() {
  function toast(message, ms = 3200) {
    text.value = message
    clearTimeout(timer)
    timer = setTimeout(() => (text.value = ''), ms)
  }
  return { text, toast }
}
