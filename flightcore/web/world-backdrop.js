'use strict';
const sceneryButton=document.getElementById('sceneryMotion');
sceneryButton.addEventListener('click',()=>{
 const paused=document.body.classList.toggle('scenery-paused');
 sceneryButton.setAttribute('aria-pressed',String(paused));
 sceneryButton.textContent=paused?'배경 재생':'배경 일시정지';
});
