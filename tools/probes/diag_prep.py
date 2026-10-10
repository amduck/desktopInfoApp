
import json
JS = """
(function(){
  var r={};
  r.boot=window.__lc_bootLog?window.__lc_bootLog.join(' ~ ').slice(-400):'(none)';
  r.temp=document.getElementById('temp')?document.getElementById('temp').textContent:'(?)';
  r.cond=document.getElementById('cond')?document.getElementById('cond').textContent.trim():'(?)';
  r.hcount=document.querySelectorAll('#hstrip .hcell, #hstrip .h').length;
  r.dcount=document.querySelectorAll('#days .card, #days .d').length;
  var it=document.querySelectorAll('#newsItems .news-item');
  r.n=it.length;
  r.badges=Array.prototype.map.call(document.querySelectorAll('#newsItems .news-badge'),function(b){return b.textContent;});
  r.first= it.length? it[0].querySelector('a').textContent.trim().slice(0,80):'(none)';
  r.href= it.length? it[0].querySelector('a').getAttribute('href').slice(0,90):'(none)';
  r.meta=document.getElementById('newsMeta')?document.getElementById('newsMeta').textContent:'(?)';
  r.pyReady=!!(window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_news==='function');
  return JSON.stringify(r);
})()
"""
open(r"C:\Users\amduc\lane-cove-weather\diag_js.json","w").write('placeholder')
print("written")
