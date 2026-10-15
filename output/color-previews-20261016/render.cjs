const {chromium}=require('C:/Users/admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const path=require('path'),{pathToFileURL}=require('url');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:960},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const folder=path.resolve('output/color-previews-20261016');
  let baseline;
  for(const [theme,name] of [['mint','01-mint-forest'],['violet','02-violet-coral'],['clay','03-cream-terracotta']]){
   await page.goto(pathToFileURL(path.join(folder,'preview.html')).href+'?layout=split&theme='+theme);
   await page.evaluate(()=>document.fonts.ready);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(theme+' horizontal overflow');
   const geometry=await page.evaluate(()=>['.workbench','.sidebar','.factory-list','.factory-detail','.detail-meta'].map(selector=>{const r=document.querySelector('.design-split '+selector)?.getBoundingClientRect()||document.querySelector(selector).getBoundingClientRect();return [r.x,r.y,r.width,r.height]}));
   if(baseline&&JSON.stringify(geometry)!==JSON.stringify(baseline))throw Error('Theme changed layout: '+theme);
   baseline=geometry;
   await page.screenshot({path:path.join(folder,name+'.png'),fullPage:true});
   console.log('PASS '+name+': identical layout, no overflow');
  }
  if(errors.length)throw Error(errors.join('\n'));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
