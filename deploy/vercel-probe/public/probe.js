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
for (const control of document.querySelectorAll('[data-provider]')) {
  control.addEventListener('click', async () => {
    const provider=control.dataset.provider;
    const output=document.getElementById(`${provider}-result`);
    control.disabled=true;
    output.textContent='검색 화면 확인 중… 최대 90초';
    try {
      const response=await fetch(`/api/${provider}`,{method:'POST',
        headers:{'X-Flight-Probe':'runtime-check'}});
      output.textContent=JSON.stringify(await response.json(),null,2);
    } catch {output.textContent='응답 미확인. 가격 없음으로 처리하지 않습니다.';}
  });
}
