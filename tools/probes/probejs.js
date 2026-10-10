
(function(){
  var r={vw:innerWidth,vh:innerHeight,checks:{}};
  function g(s){var n=document.querySelector(s);return n?n.getBoundingClientRect():null;}
  // 1) 4-day outlook rounded bottom
  var f=document.querySelector('.fore');
  r.checks.fore={overflow:getComputedStyle(f).overflow, borderRadius:getComputedStyle(f).borderRadius,
                 rect:(function(){var b=f.getBoundingClientRect();return {y:Math.round(b.y),h:Math.round(b.height)};})()};
  // 2) news nav buttons present + clickable
  r.checks.newsNav={prev:!!document.getElementById('newsPrev'), next:!!document.getElementById('newsNext'),
                    items:(document.querySelectorAll('.news-item')||[]).length};
  // 3) gallery panel
  var gs=document.querySelector('.gallerysec');
  r.checks.gallery={
    present:!!gs,
    rect:(function(){var b=gs.getBoundingClientRect();return {x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)};})(),
    prev:!!document.getElementById('galPrev'), next:!!document.getElementById('galNext'),
    imgHasSrc:(function(){var im=document.getElementById('galImg');return im && im.src && im.src.indexOf('data:image')===0;})(),
    cap:(function(){var c=document.getElementById('galCap');return c?c.textContent.slice(0,40):'';})(),
    meta:(function(){var m=document.getElementById('galMeta');return m?m.textContent.slice(0,60):'';})(),
    clickTarget:(function(){var a=document.getElementById('galLink');return a?a.getAttribute('href'):'?';})()
  };
  return JSON.stringify(r);
})()
