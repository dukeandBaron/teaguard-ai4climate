/** Typed evidence graph view; no network or record storage. */
export function createGraphView({$, labels}) {
  let current;
  let nodeSignature = "";
  let positions=new Map(), graphNodes=new Map(), dragging=null;
function nodeDescription(node){if(node.kind==='observation'){const factor=current.nature_state.context_factors.find(f=>f.id===node.id);return `${node.label}：${factor.state===null?'未知':labels[factor.state]||factor.state}。${factor.status==='UNKNOWN'?'信息尚未提供。':'该条件是AI情境声明，不能视为现场测量。'}`;}return node.detail;}
function renderGraph(reset=false){
  if(reset)positions=new Map();
  const svg=$('graph'),NS='http://www.w3.org/2000/svg';svg.replaceChildren();graphNodes=new Map(current.graph.nodes.map(n=>[n.id,n]));
  let taskIndex=0,evidenceIndex=0;
  for(const node of current.graph.nodes){if(positions.has(node.id))continue;let p;
    if(node.id==='region')p={x:140,y:95};else if(node.id==='plot')p={x:400,y:190};else if(node.kind==='evidence')p={x:730,y:55+evidenceIndex++*100};else if(node.kind==='task')p={x:1050,y:50+taskIndex++*80};else p={factor_soil:{x:140,y:260},factor_shade:{x:140,y:390},factor_growth_stage:{x:400,y:350},factor_cultivar:{x:400,y:460}}[node.id]||{x:400,y:500};positions.set(node.id,p);}
  const lines=[];
  for(const edge of current.graph.edges){const line=document.createElementNS(NS,'line');line.classList.add('graph-edge');if(edge.relation==='CONFLICTS_WITH')line.classList.add('conflict');if(edge.relation==='SUPPORTS_CHECKLIST')line.classList.add('evidence');const title=document.createElementNS(NS,'title');title.textContent=edge.label;line.append(title);svg.append(line);lines.push({edge,line});}
  const groups=new Map();
  function selectNode(node){$('node-detail').textContent=node.label+' · '+nodeDescription(node);}
  function redraw(){for(const {edge,line} of lines){const a=positions.get(edge.source),b=positions.get(edge.target);for(const [k,v] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y}))line.setAttribute(k,v);}for(const [id,g] of groups){const p=positions.get(id);g.setAttribute('transform',`translate(${p.x},${p.y})`);}}
  function point(event){const p=svg.createSVGPoint();p.x=event.clientX;p.y=event.clientY;return p.matrixTransform(svg.getScreenCTM().inverse());}
  for(const node of current.graph.nodes){const g=document.createElementNS(NS,'g');g.classList.add('graph-node',node.kind);if(node.status==='MISMATCH')g.classList.add('mismatch');if(node.status==='SIMULATED_COMPLETION')g.classList.add('completed');g.dataset.nodeId=node.id;g.setAttribute('tabindex','0');g.setAttribute('role','button');g.setAttribute('aria-label',node.label);const width=node.kind==='task'?220:node.kind==='plot'?200:180;const rect=document.createElementNS(NS,'rect');for(const [k,v] of Object.entries({x:-width/2,y:-27,width,height:54,rx:7}))rect.setAttribute(k,v);g.append(rect);
    const text=document.createElementNS(NS,'text');text.setAttribute('text-anchor','middle');const chunks=node.label.length>12?[node.label.slice(0,12),node.label.slice(12,24)]:[node.label];chunks.forEach((chunk,i)=>{const t=document.createElementNS(NS,'tspan');t.setAttribute('x','0');t.setAttribute('y',String(chunks.length===1?4:-4+i*18));t.textContent=chunk;text.append(t);});g.append(text);
    g.addEventListener('pointerdown',event=>{if(event.button!==0)return;const p=point(event),position=positions.get(node.id);dragging={id:node.id,offsetX:p.x-position.x,offsetY:p.y-position.y,startX:p.x,startY:p.y,moved:false};g.classList.add('dragging');svg.setPointerCapture(event.pointerId);event.preventDefault();});
    g.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)){selectNode(node);event.preventDefault();}const delta={ArrowLeft:[-12,0],ArrowRight:[12,0],ArrowUp:[0,-12],ArrowDown:[0,12]}[event.key];if(delta){const p=positions.get(node.id);positions.set(node.id,{x:Math.max(105,Math.min(1090,p.x+delta[0])),y:Math.max(35,Math.min(520,p.y+delta[1]))});redraw();event.preventDefault();}});
    groups.set(node.id,g);svg.append(g);
  }
  svg.onpointermove=event=>{if(!dragging)return;const p=point(event);dragging.moved ||= Math.abs(p.x-dragging.startX)+Math.abs(p.y-dragging.startY)>3;positions.set(dragging.id,{x:Math.max(105,Math.min(1090,p.x-dragging.offsetX)),y:Math.max(35,Math.min(520,p.y-dragging.offsetY))});redraw();};
  svg.onpointerup=event=>{if(!dragging)return;const node=graphNodes.get(dragging.id);groups.get(node.id).classList.remove('dragging');selectNode(node);dragging=null;if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);};
  svg.onpointercancel=()=>{dragging=null;};redraw();
}

  return {
    render(result) {
      const signature = result.graph.nodes.map(node => node.id).sort().join("|");
      const resetLayout = signature !== nodeSignature;
      current = result;
      dragging = null;
      renderGraph(resetLayout);
      nodeSignature = signature;
    },
    reset() {renderGraph(true); $("node-detail").textContent="布局已重置。拖动节点或点击查看信息。";}
  };
}
