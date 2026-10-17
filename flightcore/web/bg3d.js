/* Decorative, standalone stage-one study. Three.js r128 UMD only. */
(() => {
  'use strict';
  const canvas = document.getElementById('bg3d');
  if (!canvas) return;
  const fallback = () => {
    canvas.hidden = true;
    const note = document.getElementById('bg3dFallback');
    if (note) note.hidden = false;
  };
  if (!window.THREE || THREE.REVISION !== '128') { fallback(); return; }
  let renderer;
  try { renderer = new THREE.WebGLRenderer({canvas, alpha:true, antialias:true}); }
  catch (error) { fallback(); return; }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setClearColor(0xeaf6ff, 0);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputEncoding = THREE.sRGBEncoding;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.shadowMap.autoUpdate = false;
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0xeaf6ff, 55, 210);
  const camera = new THREE.PerspectiveCamera(26, 1, 1, 400);
  camera.position.set(0, 7, 78);
  camera.lookAt(0, 11, 0);
  const geometries = new Map(), materials = new Set();
  const geometry = (key, factory) => {
    if (!geometries.has(key)) geometries.set(key, factory());
    return geometries.get(key);
  };
  const material = (color, options = {}) => {
    const m = new THREE.MeshStandardMaterial({color, flatShading:true, roughness:.75, metalness:0, ...options});
    m.color.convertSRGBToLinear();
    if (options.emissive) m.emissive.convertSRGBToLinear();
    materials.add(m); return m;
  };
  const stone = material(0xb9c9de), lightStone = material(0xdfe8f3), darkStone = material(0x8fa3bf);
  const iron = material(0x6f84a3, {metalness:.35, roughness:.45});
  const roof = material(0x35557a);
  const clockFace = material(0xffe9cf, {emissive:0xffcf9a, emissiveIntensity:.35});
  function mesh(group, geo, mat, x, y, z) {
    const m = new THREE.Mesh(geo, mat); m.position.set(x,y,z);
    m.castShadow = true; m.receiveShadow = true; group.add(m); return m;
  }
  const unitBox = geometry('box', () => new THREE.BoxGeometry(1,1,1));
  function box(group,w,h,d,x,y,z,mat) { const m=mesh(group,unitBox,mat,x,y,z);m.scale.set(w,h,d);return m; }
  function cylinder(group,r1,r2,h,x,y,z,mat,n=8) {
    return mesh(group,geometry(`cyl:${r1}:${r2}:${h}:${n}`,()=>new THREE.CylinderGeometry(r1,r2,h,n)),mat,x,y,z);
  }
  function beam(group,a,b,width,mat) {
    const from=new THREE.Vector3(...a), to=new THREE.Vector3(...b), delta=to.clone().sub(from);
    const m=mesh(group,unitBox,mat,...from.clone().add(to).multiplyScalar(.5).toArray());
    m.scale.set(width,delta.length(),width);m.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize());return m;
  }
  function eiffel() {
    const g=new THREE.Group();g.name='EiffelTower';
    for(const x of [-1,1]) for(const z of [-1,1]) {
      beam(g,[x*6,0,z*6],[x*3,14,z*3],.8,iron);
      beam(g,[x*2.3,14.8,z*2.3],[x*1.1,27.8,z*1.1],.45,iron);
    }
    box(g,8,.8,8,0,14.4,0,iron);box(g,3.6,.6,3.6,0,28.1,0,iron);
    const arch=geometry('arch',()=>new THREE.TorusGeometry(3.5,.32,5,16,Math.PI));
    for(const z of [-4.2,4.2])mesh(g,arch,iron,0,3.8,z);
    for(const side of [-1,1]) {
      beam(g,[-4.7,5,side*4.7],[3,13.8,side*3],.27,iron);
      beam(g,[4.7,5,side*4.7],[-3,13.8,side*3],.27,iron);
      beam(g,[-2.2,15,side*2.2],[1.15,27,side*1.15],.19,iron);
      beam(g,[2.2,15,side*2.2],[-1.15,27,side*1.15],.19,iron);
    }
    cylinder(g,0,1.65,13,0,34.9,0,iron,4).rotation.y=Math.PI/4;
    cylinder(g,.09,.15,4.6,0,43.7,0,iron);
    return g;
  }
  function bigben() {
    const g=new THREE.Group();g.name='BigBenAndParliament';
    box(g,3.4,17,3.4,0,8.5,0,stone);box(g,4.6,6,4.6,0,20,0,lightStone);
    box(g,5,.4,5,0,17,0,darkStone);box(g,5,.35,5,0,23,0,darkStone);
    for(let i=0;i<4;i++) {
      const face=new THREE.Group();face.rotation.y=i*Math.PI/2;g.add(face);
      const ring=geometry('clockBorder',()=>new THREE.CircleGeometry(1.87,24));
      const disc=geometry('clockFace',()=>new THREE.CircleGeometry(1.7,24));
      mesh(face,ring,roof,0,20,2.32);mesh(face,disc,clockFace,0,20,2.34);
      box(face,.1,1.15,.06,0,20.5,2.38,roof);
      const hand=box(face,.1,.9,.06,.3,19.85,2.38,roof);hand.rotation.z=1.05;
    }
    cylinder(g,0,3.1,6.5,0,26.25,0,roof,4).rotation.y=Math.PI/4;
    cylinder(g,.06,.15,1,0,30,0,roof);
    box(g,14,6,4,8,3,-1,stone);
    for(const x of [3,13]){
      box(g,1.4,8,1.4,x,4,-1,darkStone);
      cylinder(g,0,1.25,2.7,x,9.35,-1,roof,4).rotation.y=Math.PI/4;
    }
    for(const x of [4,6,8,10,12])box(g,.45,2.2,.08,x,4,1.04,darkStone);
    return g;
  }
  const left=new THREE.Group();left.name='LeftLandmarkCluster';scene.add(left);
  const tower=eiffel(), clock=bigben();tower.position.set(-7,0,0);clock.position.set(5,0,-3);
  left.add(tower,clock);
  // Uniform presentation scale fits the requested 46-unit model inside a 26° camera.
  left.scale.setScalar(.54);
  const sun=new THREE.DirectionalLight(0xffd9b8,2.4);sun.position.set(4,16,-34);sun.castShadow=true;
  sun.shadow.mapSize.set(1024,1024);sun.shadow.camera.left=-55;sun.shadow.camera.right=30;
  sun.shadow.camera.top=50;sun.shadow.camera.bottom=-20;sun.shadow.camera.near=1;sun.shadow.camera.far=140;
  sun.shadow.bias=-.0005;scene.add(sun,sun.target);
  scene.add(new THREE.HemisphereLight(0xbfe6ff,0xf3d9c4,.85));
  const fill=new THREE.DirectionalLight(0x9ec5ff,.35);fill.position.set(-30,10,40);scene.add(fill);
  const ground=mesh(scene,geometry('ground',()=>new THREE.PlaneGeometry(260,220)),material(0xeaf6ff),0,-.06,-35);
  ground.rotation.x=-Math.PI/2;ground.castShadow=false;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const isMobile=()=>innerWidth<=767 || (navigator.hardwareConcurrency && navigator.hardwareConcurrency<=4);
  let raf=0, disposed=false, last=0, time=0, frames=0, sample=[], reported=false;
  function paused(){return document.body.classList.contains('scenery-paused') || reduced.matches;}
  function render(){renderer.shadowMap.needsUpdate=frames%4===0;renderer.render(scene,camera);frames++;}
  function tick(now){
    raf=0;if(disposed || document.hidden || paused())return;
    const interval=last ? now-last : 0;
    if(isMobile() && interval<1000/30-1){raf=requestAnimationFrame(tick);return;}
    if(last){time+=Math.min(interval,100)/1000;if(interval<250)sample.push(interval);}
    last=now;
    const angle=Math.sin(time*Math.PI*2/60)*THREE.MathUtils.degToRad(6);
    sun.position.set(4+34*Math.sin(angle),16,-34*Math.cos(angle));
    render();
    if(!reported && sample.length>=120){
      const average=sample.reduce((a,b)=>a+b,0)/sample.length;
      const metrics={revision:THREE.REVISION,triangles:renderer.info.render.triangles,averageFrameMs:+average.toFixed(2),fps:+(1000/average).toFixed(1),pixelRatio:renderer.getPixelRatio(),drawCalls:renderer.info.render.calls};
      console.info('BG3D stage 1',JSON.stringify(metrics));canvas.dataset.metrics=JSON.stringify(metrics);reported=true;
    }
    raf=requestAnimationFrame(tick);
  }
  function schedule(){cancelAnimationFrame(raf);raf=0;last=0;if(!disposed && !document.hidden && !paused())raf=requestAnimationFrame(tick);}
  function resize(){
    if(disposed)return;const w=canvas.clientWidth,h=canvas.clientHeight;
    renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();camera.updateMatrixWorld();
    // Ray/plane intersection after unproject keeps the cluster at viewport 14%.
    const point=new THREE.Vector3((w<=1280?.11:.14)*2-1,0,.5).unproject(camera);
    const direction=point.sub(camera.position).normalize();
    const distance=-camera.position.z/direction.z;
    const center=camera.position.clone().addScaledVector(direction,distance);
    left.position.x=center.x;
    left.scale.setScalar(w<=767?.27:.54);
    for(const m of [stone,lightStone,darkStone,iron,roof,clockFace]){m.transparent=w<=1280;m.opacity=w<=1280?.55:1;}
    sun.target.position.set(left.position.x*.4,8,0);renderer.shadowMap.needsUpdate=true;renderer.render(scene,camera);schedule();
  }
  const observer=new ResizeObserver(resize);observer.observe(canvas);
  const stateObserver=new MutationObserver(schedule);stateObserver.observe(document.body,{attributes:true,attributeFilter:['class']});
  document.addEventListener('visibilitychange',schedule);
  reduced.addEventListener('change',()=>{renderer.shadowMap.needsUpdate=true;renderer.render(scene,camera);schedule();});
  canvas.addEventListener('webglcontextlost',event=>{event.preventDefault();cancelAnimationFrame(raf);fallback();});
  function dispose(){disposed=true;cancelAnimationFrame(raf);observer.disconnect();stateObserver.disconnect();document.removeEventListener('visibilitychange',schedule);geometries.forEach(g=>g.dispose());materials.forEach(m=>m.dispose());sun.shadow.map?.dispose();renderer.dispose();}
  window.addEventListener('pagehide',dispose,{once:true});
  window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});
  resize();
})();
