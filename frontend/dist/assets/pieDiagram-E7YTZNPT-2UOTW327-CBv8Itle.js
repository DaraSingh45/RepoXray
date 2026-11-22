import{p as et}from"./chunk-VII2H2IX-5ppu9-DM.js";import{p as at}from"./cynefin-OW5HDTMX-GVF3BKWE-Dt2_H3LF.js";import{g as rt,s as it,a as nt,b as ot,o as st,n as lt,_ as l,l as E,c as ct,C as dt,G as gt,H as pt,d as ht,p as ft,D as ut}from"./render-O7CIS3YK-DZt5vqIV.js";import{d as U,o as mt,p as vt}from"./charts-LHQWGVn4.js";import"./mermaid-layout-elk.core-ZODMEAkK.js";import"./index-CK_KubRP.js";import"./flow-D8KjLzPD.js";var St=ut.pie,R={sections:new Map,showData:!1},T=R.sections,H=R.showData,xt=structuredClone(St),wt=l(()=>structuredClone(xt),"getConfig"),Ct=l(()=>{T=new Map,H=R.showData,ft()},"clear"),$t=l(({label:t,value:a})=>{if(a<0)throw new Error(`"${t}" has invalid value: ${a}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);T.has(t)||(T.set(t,a),E.debug(`added new section: ${t}, with value: ${a}`))},"addSection"),Dt=l(()=>T,"getSections"),yt=l(t=>{H=t},"setShowData"),Tt=l(()=>H,"getShowData"),V={getConfig:wt,clear:Ct,setDiagramTitle:lt,getDiagramTitle:st,setAccTitle:ot,getAccTitle:nt,setAccDescription:it,getAccDescription:rt,addSection:$t,getSections:Dt,setShowData:yt,getShowData:Tt},bt=l((t,a)=>{et(t,a),a.setShowData(t.showData),t.sections.map(a.addSection)},"populateDb"),At={parse:l(async t=>{const a=await at("pie",t);E.debug(a),bt(a,V)},"parse")},_t=l(t=>`
  .pieCircle{
    stroke: ${t.pieStrokeColor};
    stroke-width : ${t.pieStrokeWidth};
    opacity : ${t.pieOpacity};
  }
  .pieCircle.highlighted{
    scale: 1.05;
    opacity: 1;
  }
  .pieCircle.highlightedOnHover:hover{
    transition-duration: 250ms;
    scale: 1.05;
    opacity: 1;
  }
  .pieOuterCircle{
    stroke: ${t.pieOuterStrokeColor};
    stroke-width: ${t.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${t.pieTitleTextSize};
    fill: ${t.pieTitleTextColor};
    font-family: ${t.fontFamily};
  }
  .slice {
    font-family: ${t.fontFamily};
    fill: ${t.pieSectionTextColor};
    font-size:${t.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${t.pieLegendTextColor};
    font-family: ${t.fontFamily};
    font-size: ${t.pieLegendTextSize};
  }
`,"getStyles"),kt=_t,zt=l(t=>{const a=[...t.values()].reduce((o,m)=>o+m,0),L=[...t.entries()].map(([o,m])=>({label:o,value:m})).filter(o=>o.value/a*100>=1);return vt().value(o=>o.value).sort(null)(L)},"createPieArcs"),Et=l((t,a,L,W)=>{var I;E.debug(`rendering pie chart
`+t);const o=W.db,m=ct(),h=dt(o.getConfig(),m.pie),F=40,i=18,c=4,C=450,S=C,b=gt(a),$=b.append("g");$.attr("transform","translate("+S/2+","+C/2+")");const{themeVariables:n}=m;let[G]=pt(n.pieOuterStrokeWidth);G??(G=2);const X=h.legendPosition,M=h.textPosition,Z=h.donutHole>0&&h.donutHole<=.9?h.donutHole:0,f=Math.min(S,C)/2-F,j=U().innerRadius(Z*f).outerRadius(f),q=U().innerRadius(f*M).outerRadius(f*M),x=$.append("g");x.append("circle").attr("cx",0).attr("cy",0).attr("r",f+G/2).attr("class","pieOuterCircle");const D=o.getSections(),J=zt(D),K=[n.pie1,n.pie2,n.pie3,n.pie4,n.pie5,n.pie6,n.pie7,n.pie8,n.pie9,n.pie10,n.pie11,n.pie12];let A=0;D.forEach(e=>{A+=e});const O=J.filter(e=>(e.data.value/A*100).toFixed(0)!=="0"),_=mt(K).domain([...D.keys()]);x.selectAll("mySlices").data(O).enter().append("path").attr("d",j).attr("fill",e=>_(e.data.label)).attr("class",e=>{let r="pieCircle";return h.highlightSlice==="hover"?r+=" highlightedOnHover":h.highlightSlice===e.data.label&&(r+=" highlighted"),r}),x.selectAll("mySlices").data(O).enter().append("text").text(e=>(e.data.value/A*100).toFixed(0)+"%").attr("transform",e=>"translate("+q.centroid(e)+")").style("text-anchor","middle").attr("class","slice");const Q=$.append("text").text(o.getDiagramTitle()).attr("x",0).attr("y",-400/2).attr("class","pieTitleText"),w=[...D.entries()].map(([e,r])=>({label:e,value:r})),u=$.selectAll(".legend").data(w).enter().append("g").attr("class","legend");u.append("rect").attr("width",i).attr("height",i).style("fill",e=>_(e.label)).style("stroke",e=>_(e.label)),u.append("text").attr("x",i+c).attr("y",i-c).text(e=>o.getShowData()?`${e.label} [${e.value}]`:e.label);const v=Math.max(...u.selectAll("text").nodes().map(e=>(e==null?void 0:e.getBoundingClientRect().width)??0));let y=C,k=S+F;const s=i+c,z=w.length*s;switch(X){case"center":u.attr("transform",(e,r)=>{const d=s*w.length/2,g=-v/2-(i+c),p=r*s-d;return"translate("+g+","+p+")"});break;case"top":y+=z,u.attr("transform",(e,r)=>{const d=f,g=-v/2-(i+c),p=r*s-d;return`translate(${g}, ${p})`}),x.attr("transform",()=>`translate(0, ${z+s})`);break;case"bottom":y+=z,u.attr("transform",(e,r)=>{const d=-f-s,g=-v/2-(i+c),p=r*s-d;return"translate("+g+","+p+")"});break;case"left":k+=i+c+v,u.attr("transform",(e,r)=>{const d=s*w.length/2,g=-f-(i+c),p=r*s-d;return"translate("+g+","+p+")"}),x.attr("transform",()=>`translate(${v+i+c}, 0)`);break;case"right":default:k+=i+c+v,u.attr("transform",(e,r)=>{const d=s*w.length/2,g=12*i,p=r*s-d;return"translate("+g+","+p+")"});break}const P=((I=Q.node())==null?void 0:I.getBoundingClientRect().width)??0,Y=S/2-P/2,tt=S/2+P/2,B=Math.min(0,Y),N=Math.max(k,tt)-B;b.attr("viewBox",`${B} 0 ${N} ${y}`),ht(b,y,N,h.useMaxWidth)},"draw"),Rt={draw:Et},Bt={parser:At,db:V,renderer:Rt,styles:kt};export{Bt as diagram};
