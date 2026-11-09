import{P as $,f as Y,a as b,b as G}from"./PageHeader-DKiJRw3F.js";import{K}from"./KpiRow-DQIcqw7g.js";import{_ as q,o as X,a as J,c as v,b as L,w as z,t as d,d as I,e as a,n as E,F as x,r as M,u as R,f as C,g as Q,h as _,i as B}from"./index-d8XkejqH.js";function N(t,o,e){const s=t.createShader(o);if(t.shaderSource(s,e),t.compileShader(s),!t.getShaderParameter(s,t.COMPILE_STATUS)){const r=t.getShaderInfoLog(s);throw t.deleteShader(s),new Error(`shader: ${r}`)}return s}function V(t,o,e){const s=t.createProgram();if(t.attachShader(s,N(t,t.VERTEX_SHADER,o)),t.attachShader(s,N(t,t.FRAGMENT_SHADER,e)),t.linkProgram(s),!t.getProgramParameter(s,t.LINK_STATUS))throw new Error(`link: ${t.getProgramInfoLog(s)}`);return s}function j(t,o,e=t.STATIC_DRAW){const s=t.createBuffer();return t.bindBuffer(t.ARRAY_BUFFER,s),t.bufferData(t.ARRAY_BUFFER,o,e),s}function Z(t,o,e,s){const r=1/Math.tan(t/2),i=1/(e-s);return new Float32Array([r/o,0,0,0,0,r,0,0,0,0,(s+e)*i,-1,0,0,2*s*e*i,0])}function ee(t,o,e){const s=H(oe(t,o)),r=H(W(e,s)),i=W(s,r);return new Float32Array([r[0],i[0],s[0],0,r[1],i[1],s[1],0,r[2],i[2],s[2],0,-T(r,t),-T(i,t),-T(s,t),1])}function te(t){const o=Math.cos(t),e=Math.sin(t);return new Float32Array([o,0,-e,0,0,1,0,0,e,0,o,0,0,0,0,1])}function O(t,o){const e=new Float32Array(16);for(let s=0;s<4;s++)for(let r=0;r<4;r++)e[s*4+r]=t[r]*o[s*4]+t[4+r]*o[s*4+1]+t[8+r]*o[s*4+2]+t[12+r]*o[s*4+3];return e}const oe=(t,o)=>[t[0]-o[0],t[1]-o[1],t[2]-o[2]],W=(t,o)=>[t[1]*o[2]-t[2]*o[1],t[2]*o[0]-t[0]*o[2],t[0]*o[1]-t[1]*o[0]],T=(t,o)=>t[0]*o[0]+t[1]*o[1]+t[2]*o[2];function H(t){const o=Math.hypot(t[0],t[1],t[2])||1;return[t[0]/o,t[1]/o,t[2]/o]}function se(t){let o=0,e=0;const s=window.matchMedia("(prefers-reduced-motion: reduce)").matches,r=m=>{e||(e=m),t((m-e)/1e3),o=requestAnimationFrame(r)},i=()=>{if(cancelAnimationFrame(o),s){t(.6);return}document.hidden||(o=requestAnimationFrame(r))};return document.addEventListener("visibilitychange",i),i(),()=>{cancelAnimationFrame(o),document.removeEventListener("visibilitychange",i)}}const ne=`#version 300 es
precision highp float;
in float vAlpha;
in float vWarm;
out vec4 outColor;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = length(d);
  if (r > 0.5) discard;
  float edge = smoothstep(0.5, 0.12, r);
  // 琥珀为主，汇入环时偏白热
  vec3 cold = vec3(0.42, 0.35, 0.24);
  vec3 warm = vec3(0.93, 0.72, 0.40);
  vec3 c = mix(cold, warm, vWarm);
  outColor = vec4(c * edge, vAlpha * edge);
}`,re=`#version 300 es
precision highp float;
in vec4 aSeed;          // x: 发射器 0..2, y: 相位, z: 速度抖动, w: 是否被抑制
uniform mat4 uProj;
uniform mat4 uView;
uniform float uTime;
uniform float uSpeed;
uniform float uCull;
uniform vec3 uEmitters;  // 每台终端是否在线
uniform float uAlerts;
out float vAlpha;
out float vWarm;

void main() {
  float e = aSeed.x;
  float ph = fract(aSeed.y + uTime * uSpeed * (0.6 + aSeed.z * 0.8));
  float y0 = (e - 1.0) * 0.62;
  float z0 = (fract(aSeed.z * 7.13) - 0.5) * 0.55;

  // x 从 -5.6 走到 5.8；接近环（x≈0）时纵向收敛并涡旋
  float x = mix(-5.6, 5.8, ph);
  float conv = smoothstep(-1.7, -0.05, x);
  float swirl = exp(-pow(x / 0.72, 2.0));
  float y = y0 * (1.0 - conv) + sin(ph * 34.0 + aSeed.z * 6.28) * 0.16 * swirl;
  float z = z0 * (1.0 - conv) + cos(ph * 27.0 + aSeed.y * 6.28) * 0.16 * swirl;

  // 越过聚合环后重新散开一点，出口才不是一根发丝
  float post = smoothstep(0.7, 1.6, x);
  y += (aSeed.y - 0.5) * 0.22 * post;
  z += (fract(aSeed.z * 3.7) - 0.5) * 0.16 * post;
  vec3 pos = vec3(x, y, z);

  // 被抑制的粒子在进入聚合环之前熄灭，不参与后续流动
  float dead = step(1.0 - uCull, aSeed.w) * smoothstep(-1.1, 0.05, x);
  float em = mix(0.12, 1.0, uEmitters[int(clamp(e, 0.0, 2.0))]);

  vec4 view = uView * vec4(pos, 1.0);
  gl_Position = uProj * view;

  float depth = clamp(1.0 - (-view.z - 1.6) / 4.5, 0.0, 1.0);
  gl_PointSize = (1.1 + 2.4 * depth) * uEmitters[int(clamp(e, 0.0, 2.0))];
  vWarm = swirl * (0.55 + 0.45 * uAlerts);
  vAlpha = (1.0 - dead) * em * (0.10 + 0.55 * depth) * smoothstep(0.0, 0.08, ph) * (1.0 - smoothstep(0.92, 1.0, ph));
}`,ae=`#version 300 es
precision highp float;
in vec2 aPos;
uniform mat4 uProj;
uniform mat4 uView;
uniform float uPulse;
out float vA;
void main() {
  vec3 p = vec3(aPos.x * (0.5 + 0.02 * uPulse), aPos.y * (0.5 + 0.02 * uPulse), 0.0);
  gl_Position = uProj * uView * vec4(p, 1.0);
  vA = 0.55 + 0.45 * uPulse;
}`,ie=`#version 300 es
precision highp float;
in float vA;
out vec4 outColor;
void main() { outColor = vec4(0.91, 0.71, 0.36, vA); }`,U=14e3;function le(t,o={}){const e=t.getContext("webgl2",{antialias:!1,alpha:!0,premultipliedAlpha:!0,powerPreference:"low-power"});if(!e)return ce(t);const s=V(e,re,ne),r=V(e,ae,ie),i=new Float32Array(U*4);for(let n=0;n<U;n++)i[n*4]=n%3,i[n*4+1]=Math.random(),i[n*4+2]=Math.random(),i[n*4+3]=Math.random();const m=j(e,i),c={seed:e.getAttribLocation(s,"aSeed"),proj:e.getUniformLocation(s,"uProj"),view:e.getUniformLocation(s,"uView"),time:e.getUniformLocation(s,"uTime"),speed:e.getUniformLocation(s,"uSpeed"),cull:e.getUniformLocation(s,"uCull"),emitters:e.getUniformLocation(s,"uEmitters"),alerts:e.getUniformLocation(s,"uAlerts")},u={pos:e.getAttribLocation(r,"aPos"),proj:e.getUniformLocation(r,"uProj"),view:e.getUniformLocation(r,"uView"),pulse:e.getUniformLocation(r,"uPulse")},f=new Float32Array(194);for(let n=0;n<=96;n++){const l=n/96*Math.PI*2;f[n*2]=Math.cos(l),f[n*2+1]=Math.sin(l)}const F=j(e,f),h={speed:.075,cull:.12,alerts:.2,emitters:[1,1,1]};function A(){const n=Math.min(window.devicePixelRatio||1,2),l=Math.max(1,Math.round(t.clientWidth*n)),p=Math.max(1,Math.round(t.clientHeight*n));return(t.width!==l||t.height!==p)&&(t.width=l,t.height=p),e.viewport(0,0,l,p),l/p}let w=2.2;const y=new ResizeObserver(()=>{w=A()});y.observe(t),w=A();const g=ee([0,.5,4.6],[0,0,0],[0,1,0]),S=n=>{const D=Math.max(1.2,Math.min(4,11.8/n));return Z(2*Math.atan(D/2/4.6),n,.1,20)};let P=S(w);e.clearColor(0,0,0,0),e.enable(e.BLEND),e.blendFunc(e.SRC_ALPHA,e.ONE);const k=se(n=>{const l=A();(l!==w||!P)&&(w=l,P=S(l)),e.clear(e.COLOR_BUFFER_BIT);const p=O(P,O(g,te(Math.sin(n*.08)*.1)));e.useProgram(s),e.bindBuffer(e.ARRAY_BUFFER,m),e.enableVertexAttribArray(c.seed),e.vertexAttribPointer(c.seed,4,e.FLOAT,!1,0,0),e.uniformMatrix4fv(c.proj,!1,p),e.uniformMatrix4fv(c.view,!1,g),e.uniform1f(c.time,n),e.uniform1f(c.speed,h.speed),e.uniform1f(c.cull,h.cull),e.uniform1f(c.alerts,h.alerts),e.uniform3f(c.emitters,...h.emitters),e.drawArrays(e.POINTS,0,U),e.useProgram(r),e.bindBuffer(e.ARRAY_BUFFER,F),e.enableVertexAttribArray(u.pos),e.vertexAttribPointer(u.pos,2,e.FLOAT,!1,0,0),e.uniformMatrix4fv(u.proj,!1,p),e.uniformMatrix4fv(u.view,!1,g),e.uniform1f(u.pulse,.5+.5*Math.sin(n*1.4)*(.4+h.alerts)),e.drawArrays(e.LINE_STRIP,0,97),e.uniform1f(u.pulse,.25+.25*Math.sin(n*1.4)),e.drawArrays(e.LINE_STRIP,0,97)});return{setData(n){const l=Math.max(1,n.batches||1);h.speed=.05+Math.min(.09,l/9e3),h.cull=Math.min(.6,(n.suppressed||0)/(l*3)),h.alerts=Math.min(1,(n.alerts||0)/20),h.emitters=[0,1,2].map(p=>n.online&&n.online[p]?1:.12)},destroy(){k(),y.disconnect()}}}function ce(t,o){const e=t.getContext("2d"),s=()=>{const i=Math.min(window.devicePixelRatio||1,2);t.width=t.clientWidth*i,t.height=t.clientHeight*i,e.scale(i,i);const m=t.clientWidth,c=t.clientHeight;e.clearRect(0,0,m,c),e.strokeStyle="rgba(232,180,92,0.5)",e.lineWidth=1;for(let u=0;u<3;u++){const f=c*(.25+u*.25);e.beginPath(),e.moveTo(m*.08,f),e.bezierCurveTo(m*.35,f,m*.4,c/2,m*.5,c/2),e.stroke()}e.beginPath(),e.arc(m/2,c/2,Math.min(m,c)*.16,0,Math.PI*2),e.strokeStyle="rgba(232,180,92,0.8)",e.stroke()},r=new ResizeObserver(s);return r.observe(t),s(),{setData(){},destroy(){r.disconnect()}}}const ue={key:0,class:"error"},de={class:"md-card flow-card"},me={class:"flow-head"},fe={class:"md-card lanes"},he={class:"lane-grid"},pe={class:"md-chip"},ve={class:"md-mono md-muted"},_e=["aria-label"],we={class:"lane-meta"},Ae={class:"lane-metrics"},ge={class:"unit"},Pe={class:"md-card"},be={class:"md-list"},ye={class:"md-grow"},Se={class:"md-muted small"},xe={key:0,class:"md-muted empty"},ke={class:"md-muted small hint"},Me={__name:"Overview",setup(t){const o=C(null),e=C(""),s=C(null);let r=null;const i=async()=>{try{o.value=await G("/overview"),e.value="",r&&o.value&&r.setData({batches:o.value.batches_24h,suppressed:o.value.suppressed_buckets,alerts:o.value.alerts_24h,online:o.value.lanes.map(u=>u.online)})}catch(u){e.value=u.message}};X(async()=>{s.value&&(r=le(s.value)),await i(),m=setInterval(i,15e3)});let m=0;J(()=>{var u;clearInterval(m),(u=r==null?void 0:r.destroy)==null||u.call(r)});const c=()=>o.value?[{label:"在线终端",value:`${o.value.devices_online}/${o.value.devices_total}`,note:"最近 15 分钟有批次"},{label:"24 h 批次",value:b(o.value.batches_24h,0),note:"按 (device, batch_id) 去重"},{label:"24 h 建议",value:b(o.value.advice_24h,0),note:`其中告警 ${o.value.alerts_24h}`},{label:"被抑制的桶",value:b(o.value.suppressed_buckets,0),note:"k<5，只在端内使用"}]:[];return(u,f)=>{var h,A,w,y,g,S,P,k;const F=Q("RouterLink");return _(),v(x,null,[L($,{title:"总览",sub:`${((h=o.value)==null?void 0:h.edge_name)||"边节点"} · 3 台终端 · 5 分钟聚合窗口 · k≥5 才入库`},{default:z(()=>[a("button",{class:"md-btn md-btn--tonal",onClick:i},"刷新"),L(F,{class:"md-btn",to:"/settings"},{default:z(()=>[...f[0]||(f[0]=[B("上云设置",-1)])]),_:1})]),_:1},8,["sub"]),e.value?(_(),v("p",ue,"读不到总览："+d(e.value),1)):I("",!0),L(K,{items:c()},null,8,["items"]),a("section",de,[a("div",me,[f[1]||(f[1]=a("div",null,[a("h2",null,"数据流"),a("p",{class:"md-muted"},"端 → k≥5 聚合环 → 云。熄掉的粒子是被抑制的桶。")],-1)),a("span",{class:E(["md-chip",(A=o.value)!=null&&A.cloud_ok?"md-chip--ok":"md-chip--warn"])},d((w=o.value)!=null&&w.cloud_ok?"云端可达":"云端未连"),3)]),a("canvas",{ref_key:"flowHost",ref:s,class:"flow-canvas"},null,512)]),a("section",fe,[f[2]||(f[2]=a("div",{class:"section-head"},[a("h2",null,"链路"),a("span",{class:"md-muted"},"最近 24 个 5 分钟窗口 · 实心格为已收到")],-1)),a("div",he,[(_(!0),v(x,null,M(((y=o.value)==null?void 0:y.lanes)||[],n=>(_(),v("article",{key:n.device_id,class:"lane"},[a("header",null,[a("strong",null,d(n.name),1),a("span",pe,d(n.scene),1),a("span",ve,d(n.device_id),1)]),a("div",{class:"ticks","aria-label":`${n.device_id} 最近 24 个窗口`},[(_(!0),v(x,null,M(n.ticks,(l,p)=>(_(),v("span",{key:p,class:E(["tick",{"tick--on":l}])},null,2))),128))],8,_e),a("div",we,[a("span",null,"最小 k "+d(n.k),1),a("span",null,d(n.fill)+"% 到达",1)]),a("dl",Ae,[(_(!0),v(x,null,M(n.metrics.slice(0,4),l=>(_(),v("div",{key:l.metric},[a("dt",null,d(l.label),1),a("dd",null,[B(d(R(b)(l.mean,l.decimals)),1),a("span",ge,d(l.unit),1)])]))),128))])]))),128))])]),a("section",Pe,[f[3]||(f[3]=a("div",{class:"section-head"},[a("h2",null,"24 h 里最值得说的三件事"),a("span",{class:"md-muted"},"相对 7 天同段基线")],-1)),a("div",be,[(_(!0),v(x,null,M(((g=o.value)==null?void 0:g.findings)||[],n=>(_(),v("div",{key:n.metric,class:"md-list-row"},[a("div",ye,[a("div",null,d(n.text),1),a("div",Se,d(n.label)+" · "+d(n.delta>0?"+":"")+d(R(b)(n.delta,2))+d(n.unit),1)]),a("span",{class:E(["md-chip",Math.abs(n.pct)>3?"md-chip--warn":""])},d(n.pct>0?"+":"")+d(R(b)(n.pct,1))+"% ",3)]))),128)),(P=(S=o.value)==null?void 0:S.findings)!=null&&P.length?I("",!0):(_(),v("p",xe,"还没有足够的数据生成结论。"))]),a("p",ke," 比较口径：每个指标取最近 24 h 均值，对照同设备前 7 天同一时段的均值。 最近一次更新 "+d(R(Y)((k=o.value)==null?void 0:k.generated_at,!0))+"。 ",1)])],64)}}},Ee=q(Me,[["__scopeId","data-v-cb91fdfa"]]);export{Ee as default};
