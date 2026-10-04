const fs=require('fs'),path=require('path');
const locale=process.argv[2]||'zh', suffix=locale==='en'?'-en':'', mathDir='math'+suffix;
const W=process.env.VALUE_METHODOLOGY_WORK||__dirname;
const mj=path.dirname(require.resolve('mathjax-full/package.json'));
const {mathjax}=require(mj+'/js/mathjax.js');const {TeX}=require(mj+'/js/input/tex.js');const {SVG}=require(mj+'/js/output/svg.js');
const {liteAdaptor}=require(mj+'/js/adaptors/liteAdaptor.js');const {RegisterHTMLHandler}=require(mj+'/js/handlers/html.js');const {AllPackages}=require(mj+'/js/input/tex/AllPackages.js');
const sharp=require('sharp');
const adaptor=liteAdaptor();RegisterHTMLHandler(adaptor);
const doc=mathjax.document('',{InputJax:new TeX({packages:AllPackages}),OutputJax:new SVG({fontCache:'none'})});
const esc=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
fs.mkdirSync(path.join(W,mathDir),{recursive:true});
async function run(){
const {marked}=await import(require.resolve('marked'));let eqs=[],chapters=[];
for(const ch of JSON.parse(fs.readFileSync(path.join(W,'chapters'+suffix+'.json'),'utf8'))){
 let source=ch.markdown;const fences=[];source=source.replace(/```[\s\S]*?```/g,m=>{fences.push(m);return 'FENCERESTORETOKEN'+(fences.length-1)+'END';});
 source=source.replace(/\*\*([^\n]+?)\*\*/g,'<strong>$1</strong>');
 // Display and inline mathematics are replaced before Markdown can consume TeX backslashes.
 source=source.replace(/\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|(?<!\\)\$([^$\n]+?)\$/g,(whole,a,b,c,d)=>{
  let tex=(a??b??c??d).trim(),display=c===undefined&&d===undefined,id='eq-'+String(eqs.length+1).padStart(3,'0');
  const node=doc.convert(tex,{display,em:16,ex:8,containerWidth:720});
  let svg=adaptor.outerHTML(adaptor.firstChild(node));
  const err=svg.includes('data-mjx-error');if(err)throw new Error('Math error '+id+' '+tex);
  const view=/viewBox="([^"]+)"/.exec(svg)[1].split(' ').map(Number);
  const w=parseFloat(/width="([\d.]+)ex"/.exec(svg)?.[1]||'10')*8;
  const h=parseFloat(/height="([\d.]+)ex"/.exec(svg)?.[1]||'3')*8;
  svg=svg.replace(/width="[^"]+"/,`width="${w}px"`).replace(/height="[^"]+"/,`height="${h}px"`).replace(/currentColor/g,'#111111');
  svg=svg.replace(/ role="[^"]*"/g,'').replace(/ aria-label="[^"]*"/g,'').replace('<svg ',`<svg role="img" aria-label="${esc(tex)}" `);
  fs.writeFileSync(path.join(W,mathDir,id+'.svg'),svg);
  eqs.push({id,tex,display,width:w,height:h});
  return display?'\n\n<div class="equation" data-equation="'+id+'"><img src="'+mathDir+'/'+id+'.svg" alt="'+esc(tex)+'"></div>\n\n':'<img class="inline-equation" style="width:'+w/16+'em;height:'+h/16+'em" data-equation="'+id+'" src="'+mathDir+'/'+id+'.svg" alt="'+esc(tex)+'">';
 });
 source=source.replace(/FENCERESTORETOKEN(\d+)END/g,(x,n)=>fences[Number(n)]);
 let html=marked.parse(source,{gfm:true,breaks:false});
 // chapter headings are h2 on the website, retaining one page h1.
 html=html.replace(/<h([1-6])>([\s\S]*?)<\/h\1>/g,(x,n,s)=>`<h${Number(n)+1}>${s}</h${Number(n)+1}>`);
 chapters.push({...ch,html});
}
for(const e of eqs){await sharp(path.join(W,mathDir,e.id+'.svg'),{density:300}).png().toFile(path.join(W,mathDir,e.id+'.png'));}
fs.writeFileSync(path.join(W,'rendered'+suffix+'.json'),JSON.stringify({chapters,equations:eqs},null,2));
console.log(JSON.stringify({chapters:chapters.length,equations:eqs.length,wide:eqs.filter(x=>x.width>900).map(x=>({id:x.id,width:x.width,tex:x.tex}))}));
}run().catch(e=>{console.error(e);process.exit(1)});
