const button = document.getElementById('check');
const result = document.getElementById('result');
button.addEventListener('click', async () => {
  button.disabled = true;
  result.textContent = 'Chrome 실행 확인 중…';
  try {
    const response = await fetch('/api/browser', {method: 'POST',
      headers: {'X-Flight-Probe': 'runtime-check'}});
    const data = await response.json();
    result.textContent = JSON.stringify(data, null, 2);
  } catch { result.textContent = '응답을 확인하지 못했습니다. 배포 로그 확인이 필요합니다.'; }
});
