import unittest
import pathlib
import shutil
import subprocess
from types import SimpleNamespace
import studio_features as f


class FeatureTests(unittest.TestCase):
    def test_missing_engagement_is_not_zero(self):
        rows=[{'views':100,'likes':10,'comments':2,'seconds':300},
              {'views':10000,'likes':None,'comments':1,'seconds':300}]
        result=f.summary(rows)
        self.assertEqual(result['engagement_rate'],12)
        self.assertEqual(result['complete_engagement_videos'],1)
        self.assertIsNone(f.summary([rows[1]])['engagement_rate'])

    def test_weighted_rates_and_separate_missing_count_coverage(self):
        rows=[{'id':'a','views':100,'likes':10,'comments':2},
              {'id':'b','views':900,'likes':9,'comments':9},
              {'id':'c','views':1000,'likes':None,'comments':20}]
        result=f.summary(rows, 'Test public sample')
        self.assertEqual(result['engagement_rate'],3)
        self.assertEqual(result['like_rate'],1.9)
        self.assertEqual(result['comment_rate'],1.55)
        self.assertEqual(result['engagement_denominator_views'],1000)
        self.assertEqual(result['comment_rate_denominator_views'],2000)
        self.assertEqual(result['engagement_excluded_videos'],1)
        self.assertEqual(result['source_scope'],'Test public sample')
        self.assertEqual(result['source_video_ids'],['a','b','c'])

    def test_unknown_counts_duration_and_best_video_stay_unknown(self):
        rows=[{'views':None,'seconds':None}, {'views':float('nan')},
              {'views':-1,'seconds':0}, {'views':True,'seconds':-1}]
        result=f.summary(rows)
        self.assertIsNone(result['best_video'])
        self.assertIsNone(result['median_views'])
        self.assertEqual(result['duration_unknown_videos'],4)
        self.assertEqual(result['short_duration_count'],0)
        self.assertEqual(result['views_missing_videos'],4)
        zero=f.summary([{'views':0,'likes':100,'comments':100}])
        self.assertIsNone(zero['engagement_rate'])
        self.assertEqual(zero['complete_engagement_videos'],0)
        self.assertEqual(zero['median_views'],0)
        empty=f.summary([])
        self.assertIsNone(empty['published_from'])
        self.assertIsNone(empty['uploads_per_week'])

    def test_cadence_uses_only_valid_observed_dates(self):
        result=f.summary([{'published':'2026-01-01T00:00:00Z'},
                          {'published':'2026-01-08T00:00:00'},
                          {'published':'not a date'}, {'published':None}])
        self.assertEqual(result['dated_videos'],2)
        self.assertEqual(result['observed_span_days'],7)
        self.assertEqual(result['uploads_per_week'],1)
        self.assertIn('+00:00',result['published_from'])
        self.assertIsNone(f.summary([{'published':'2026-01-01'}]*2)['uploads_per_week'])

    def test_zero_views_has_no_ratio(self):
        self.assertIsNone(f.rate(0,0))
        self.assertEqual(f.rate(0,100),0)

    def test_tags_count_quotes_spaces_and_commas(self):
        self.assertEqual(f.tag_length(['foo','foo bar']),13)
        self.assertEqual(f.tag_length([]),0)

    def test_timestamp_formats_and_invalid_seconds(self):
        self.assertEqual(f.timestamp('1:23'),83)
        self.assertEqual(f.timestamp('1h2m3s'),3723)
        self.assertEqual(f.timestamp('00:01:23,125'),83.125)
        with self.assertRaises(ValueError): f.timestamp('1:99')

    def test_chapter_final_length_needs_duration(self):
        txt='00:00 Intro\n00:10 First\n00:20 Second'
        self.assertIsNone(f.chapters(txt)['checks'][-1][1])
        self.assertFalse(f.chapters(txt,25)['valid'])
        self.assertTrue(f.chapters(txt,30)['valid'])
        self.assertFalse(f.chapters('00:00 A\n00:05 B\n00:10 C',30)['valid'])

    def test_vtt_preserves_original_cue_times(self):
        cues=f.parse_vtt('WEBVTT\n\n00:00:01.250 --> 00:00:03.500 align:start\n<c>Hello &amp; world</c>\n\n00:00:04.000 --> 00:00:04.000\nBad cue\n')
        self.assertEqual(cues,[{'start':1.25,'end':3.5,'text':'Hello & world'}])

    def test_incomplete_replies_never_mean_unanswered(self):
        def comment(cid,author):return {'id':cid,'snippet':{'authorChannelId':{'value':author},'textDisplay':'Hello','likeCount':0}}
        threads=[{'snippet':{'topLevelComment':comment('a','viewer'),'totalReplyCount':2},'replies':{'comments':[comment('r','other')]}},
                 {'snippet':{'topLevelComment':comment('b','viewer'),'totalReplyCount':0}},
                 {'snippet':{'topLevelComment':comment('c','viewer'),'totalReplyCount':5},'replies':{'comments':[comment('r2','owner')]}}]
        host=SimpleNamespace(video_id=lambda q:'vid',videos=lambda ids:[{'channel_id':'owner'}],api=lambda *a,**kw:{'items':threads})
        result=f.run(host,'comments-rich',{'q':'video'})
        self.assertEqual([r['owner_replied'] for r in result['rows']],[None,False,True])

    def test_no_public_handle_is_not_availability(self):
        host=SimpleNamespace(api=lambda *a,**kw:{'items':[]})
        result=f.run(host,'handle-batch',{'q':'@examplehandle'})
        self.assertIn('unknown',result['handles'][0]['status'])

    @unittest.skipUnless(shutil.which('node'), 'Node is required for isolated JavaScript tests')
    def test_shared_source_context_javascript(self):
        # A minimal in-memory DOM and mocked gateway: no browser, credentials or network.
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements=new Map();let nodes=[];
class Element {
 constructor(tag='div'){this.tagName=tag;this.value='';this.textContent='';this.dataset={};this.children=[];this.isConnected=true;this.selectionStart=0;this.selectionEnd=0;nodes.push(this)}
 set id(v){this._id=v;elements.set(v,this)} get id(){return this._id}
 set innerHTML(v){this._html=v;for(const m of v.matchAll(/id="([^"]+)"/g)){const e=new Element();e.id=m[1]}for(const m of v.matchAll(/data-source-fetch="([^"]+)"/g)){const b=new Element('button');b.dataset.sourceFetch=m[1]}}
 get innerHTML(){return this._html||''}
 append(...children){this.children.push(...children)}
 before(e){this.beforeElement=e}
 replaceChildren(...children){this.children=children;this.textContent=children.map(e=>e.textContent||'').join('')}
 setAttribute(k,v){this[k]=v}
 insertAdjacentHTML(where,html){this._html=(this._html||'')+html}
 querySelector(q){return q.startsWith('#')?elements.get(q.slice(1)):null}
 querySelectorAll(q){if(q.includes('data-source-fetch'))return nodes.filter(n=>n.dataset.sourceFetch);if(q.includes('data-source-insert'))return nodes.filter(n=>n.dataset.sourceInsert);return []}
}
const storage=new Map(),sandbox={assert,console,Element,elements,
 document:{createElement:t=>new Element(t),createTextNode:text=>({textContent:text}),getElementById:id=>elements.get(id),addEventListener:()=>{}},
 localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
 window:{confirm:()=>true},URL,setInterval:()=>{},clearInterval:()=>{},setTimeout:()=>{},
 $:q=>q.startsWith('#')?elements.get(q.slice(1)):null,
 toolOpen:()=>{},toolRun:()=>{},renderToolResult:(t,r)=>{elements.get('tool-result').innerHTML=r.html||''},localTool:()=>{},calculateTool:()=>{},imageTool:()=>{},toolExport:()=>{},
 proToolActions:()=>{},proCaptureTool:()=>{},proEnhanceLegacy:()=>{},
 sx:s=>String(s??'').replaceAll('<','&lt;'),snote:s=>String(s),table:(h,r)=>JSON.stringify(r),sn:s=>String(s),smetric:()=>'',sempty:(h,t)=>h+' '+t,
 ST:{busy:false,tool:null},STUDIO_TOOLS:[],PRO:{toolState:new Map()},toast:()=>{},
 svalue:id=>elements.get('sf-'+id)?.value||'',
 extractVideo:q=>String(q).match(/(?:v=|youtu\.be\/)([\w-]{11})/)?.[1]||null,
 mountBase:(id,q)=>{for(const e of elements.values())e.isConnected=false;elements.clear();nodes=[];for(const k of ['studio-form','tool-run','tool-result','sf-q','sf-language','ef-context','ef-wpm']){const e=new Element();e.id=k}elements.get('sf-q').value=q;elements.get('sf-language').value='English';},
};
vm.createContext(sandbox);
vm.runInContext(`
var requests=[],gateway=null;
async function jp(url,data){requests.push(data);return gateway?await gateway(data):data.kind==='source-context'?{text:'00:00 Intro\\n00:10 Body\\n00:20 End',kind:'subtitles',source:'Mock original captions',vid:'abcdefghijk',cues:[{start:0,end:10,text:'Intro'},{start:10,end:20,text:'Body'},{start:20,end:30,text:'End'}]}:{text:'00:00 Intro\\n00:10 Body\\n00:20 End'};}
`,sandbox);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);
vm.runInContext(`
(async()=>{
 const ai=['hashtags','titles','tags','description','channel-description','names','reply','chapters','translate','summary','ideas','hooks','script-review','script'];
 STUDIO_TOOLS=EF_COVERAGE.map(t=>({...t,mode:ai.includes(t.id)?'ai':t.id==='title-score'?'local':['resize','banner','image-check'].includes(t.id)?'image':t.id==='money'?'calc':'video'}));
 function mount(id,q=''){mountBase(id,q);ST.tool=id;ST.busy=false;ST.result=null;EFS.epoch++;EFS.run=null;EFS.pending=null;EFS.insertedQ=null;EFS.insertedContext=null;efSourceMount();}
 function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve}}
 const url='https://youtu.be/abcdefghijk';
 assert.equal(efSourceVideo(url),'abcdefghijk');
 assert.equal(efSourceVideo('abcdefghijk'),'abcdefghijk');
 assert.equal(efSourceVideo('https://example.com/watch?v=abcdefghijk'),null);
 assert.equal(efSourceVideo('Discuss '+url),null);
 const ocr=efSourceNormalize({text:'00:00 screen clock',kind:'ocr',cues:[{start:0,end:1,text:'screen'}]},'ocr',url);
 assert.equal(ocr.kind,'screen-ocr');assert.equal(ocr.cues.length,0);
 assert.equal(efSourceMetadata(ocr).timing,'none');
 assert.throws(()=>efSourceRequireTiming(ocr,ocr.text),/Screen OCR/);
 assert.throws(()=>efSourceNormalize({text:'screen',kind:'screen-ocr'},'subtitles',url),/requested/);
 assert.throws(()=>efSourceNormalize({text:''},'subtitles',url),/No source/);
 assert.throws(()=>efSourceRequireTiming(null,'Untimed text'),/timestamps/);
 for(const t of STUDIO_TOOLS){mount(t.id,'original input');assert.ok($('#esc-panel'),t.id);assert.equal(svalue('q'),'original input');if(t.mode!=='ai'&&t.id!=='title-score')assert.equal(nodesForActions().length,0)}
 function nodesForActions(){return $('#esc-panel').querySelectorAll('[data-source-insert]')}
 assert.equal(STUDIO_TOOLS.length,70);
 window.CL_ACTIVE_CHANNEL='own-a';mount('summary');EFS.context={...efSourceEmpty(),text:'<img src=x onerror=alert(1)>',source:'User text'};efSourceSave();efSourceRender();
 assert.ok($('#esc-preview').textContent.includes('<img'));assert.equal($('#esc-preview').innerHTML,'');
 window.CL_ACTIVE_CHANNEL='own-b';efSourceCurrent();assert.equal(EFS.context.text,'');EFS.context.text='B';efSourceSave();
 window.CL_ACTIVE_CHANNEL='own-a';efSourceCurrent();assert.ok(EFS.context.text.includes('<img'));
 window.CL_ACTIVE_CHANNEL='own-b';efSourceCurrent();assert.equal(EFS.context.text,'B');efSourceClear();
 window.CL_ACTIVE_CHANNEL='own-a';efSourceCurrent();assert.ok(EFS.context.text.includes('<img'));
 // Updating the query does not reattribute existing evidence to another video.
 EFS.context.video_url=url;EFS.context.input_url=url;efSourceRender();$('#esc-video').value='https://youtu.be/lmnopqrstuv';efSourceEdited('video');assert.equal(EFS.context.video_url,url);
 for(const id of ai){mount(id,url);requests=[];await toolRun();assert.equal(requests.length,2,id);assert.equal(requests[0].kind,'source-context');assert.equal(requests[0].method,'subtitles');assert.equal(requests[1].kind,'ai');assert.ok(requests[1].q.includes('Mock original captions'));assert.equal(ST.result.source_context[0].kind,'subtitles');assert.equal(ST.busy,false)}
 mount('ideas','Preserve this goal');EFS.context={...efSourceEmpty(),text:'shared facts'};efSourceInsert('q');requests=[];await toolRun();assert.ok(requests[0].q.includes('Preserve this goal'));assert.equal(ST.result.source_context[0].kind,'pasted-text');
 mount('tags','topic');EFS.context=ocr;efSourceInsert('context');const once=$('#ef-context').value;efSourceInsert('context');assert.equal($('#ef-context').value,once);requests=[];await toolRun();assert.ok(requests[0].q.includes('screen-ocr'));assert.equal(ST.result.source_context[0].timing,'none');
 mount('summary','topic');EFS.context=ocr;$('#esc-attach').checked=true;requests=[];await toolRun();assert.equal(requests[0].kind,'ai');assert.equal(requests[0].source_context[0].kind,'screen-ocr');
 mount('chapters','00:00 looks timed');EFS.context=ocr;$('#esc-attach').checked=true;requests=[];await toolRun();assert.equal(requests.length,0);assert.ok($('#tool-result').textContent.includes('Screen OCR'));
 mount('summary',url);requests=[];const old=deferred();gateway=()=>old.promise;const work=toolRun();await toolRun();assert.equal(requests.length,1);mount('tags','new task');mount('summary','different task');old.resolve({text:'late captions',kind:'subtitles'});await work;assert.equal(requests.length,1);assert.equal(ST.result,null);
 mount('summary');EFS.context={...efSourceEmpty(),text:'keep me',video_url:url,input_url:url};efSourceRender();requests=[];const pending=deferred();gateway=()=>pending.promise;const fetching=efSourceFetch('subtitles');await efSourceFetch('subtitles');assert.equal(requests.length,1);efSourceClear();pending.resolve({text:'too late',kind:'subtitles'});await fetching;assert.equal(EFS.context.text,'');
 EFS.context={...efSourceEmpty(),text:'saved evidence',video_url:url,input_url:url};efSourceRender();gateway=()=>({error:'mock failure'});await efSourceFetch('subtitles');assert.equal(EFS.context.text,'saved evidence');assert.equal(EFS.pending,null);assert.ok($('#esc-status').textContent.includes('mock failure'));
 const saving=localStorage.setItem;localStorage.setItem=()=>{throw Error('quota')};assert.equal(efSourceSave(),false);assert.ok($('#esc-status').textContent.includes('could not save'));localStorage.setItem=saving;
 function input(id,value){const e=new Element();e.id=id;e.value=value;return e}
 const description='\\n  Original\\r\\n'+('line <b>literal</b> & text\\n'.repeat(250))+'LAST MARKER  ';
 const tags=Array.from({length:64},(_,i)=>i===0?'two, words':i===63?'Last Applied TAG':'Tag '+i);
 const video={id:'abcdefghijk',title:'Not an applied keyword',channel:'Creator',description,tags,seconds:60,views:1};
 mount('video-pack',url);gateway=()=>({video});requests=[];await efVideoPackRun();
 assert.equal($('#vp-description-text').textContent,description);assert.equal($('#vp-keywords-text').textContent,tags.join(', '));
 assert.equal((efPackHtml(ST.result).match(/class="studio-chip"/g)||[]).length,64);assert.equal(typeof efPackKeywords,'undefined');
 assert.ok(efPackHtml(ST.result).includes('no words are guessed'));
 video.description='';video.tags=[];await efVideoPackRun();assert.ok($('#vp-description-text').textContent.includes('no description'));assert.ok($('#vp-keywords-text').textContent.includes('no applied'));
 for(const engine of ['local','api']){
  gateway=d=>({ok:true,text:'00:00 Visible text',kind:'ocr',engine:d.engine,frames:1,step:12,cached:true});
  mount('summary',url);$('#esc-video').value=url;$('#esc-ocr-engine').value=engine;requests=[];await efSourceFetch('ocr');
  assert.equal(requests[0].engine,engine);assert.equal(EFS.context.kind,'screen-ocr');assert.ok(EFS.context.source.includes(engine==='api'?'Gemini':'Local'));
  mount('transcript',url);input('ef-ocr-engine',engine);requests=[];await efTranscriptOcr();
  assert.equal(requests[0].engine,engine);assert.equal(ST.result.engine,engine);assert.equal(ST.busy,false);
  assert.ok($('#tool-result').innerHTML.includes(engine==='api'?'Saved API OCR cache':'Saved local OCR cache'));
  mount('video-pack',url);ST.result={vid:'abcdefghijk',video};input('vp-ocr-engine',engine);input('vp-ocr-btn','');input('vp-ocr','');requests=[];await efPackOcr();
  assert.equal(requests[0].engine,engine);assert.equal(ST.result.ocr.engine,engine);assert.equal(ST.busy,false);
  assert.ok($('#vp-ocr').innerHTML.includes(engine==='api'?'API (Gemini vision)':'Screen OCR · local'));
 }
 window.confirm=()=>false;
 for(const path of ['source','transcript','pack']){
  mount(path==='source'?'summary':path==='pack'?'video-pack':'transcript',url);requests=[];
  $('#esc-video').value=url;$('#esc-ocr-engine').value='api';input('ef-ocr-engine','api');input('vp-ocr-engine','api');input('vp-ocr-btn','');input('vp-ocr','');ST.result={vid:'abcdefghijk',video};
  await (path==='source'?efSourceFetch('ocr'):path==='pack'?efPackOcr():efTranscriptOcr());assert.equal(requests.length,0,path);assert.equal(ST.busy,false);assert.equal(EFS.pending,null);
 }
 window.confirm=()=>true;mount('transcript',url);input('ef-ocr-engine','api');gateway=()=>({error:'Gemini unavailable; no local fallback'});await efTranscriptOcr();assert.equal(ST.busy,false);assert.ok($('#tool-result').textContent.includes('no local fallback'));
 console.log('Shared context: 70 panels, 14 AI paths, exact metadata, local/API routing in three OCR paths, consent, isolation, timing, stale/duplicate/error checks passed.');
})()
`,sandbox).catch(e=>{console.error(e);process.exitCode=1});
'''
        path=pathlib.Path(__file__).resolve().with_name('studio_features.js')
        result=subprocess.run(['node','-',str(path)],input=script,text=True,encoding='utf-8',capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)


class ResponsiveLayoutTests(unittest.TestCase):
    def test_full_width_grid_and_unclipped_metrics(self):
        import ast
        import re
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest('Playwright is required for browser layout tests')
        root = pathlib.Path(__file__).resolve().parent
        tree = ast.parse((root / 'clicklab.py').read_text(encoding='utf-8-sig'))
        page_source = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == 'PAGE' for t in n.targets))
        css = '\n'.join(re.findall(r'<style>(.*?)</style>', page_source, re.S))
        css += '\n' + (root / 'studio.css').read_text(encoding='utf-8')
        cards = '<article class="cw-video-card"><div class="cw-video-image"></div><div class="cw-video-body">Evidence video</div></article>' * 12
        metrics = ''.join('<div class="studio-metric"><span>Public count</span><strong>' + value + '</strong></div>'
                          for value in ['1,835,681,400', '19,498,162', '2,461,824', '03:34', '10/25/2009'])
        html = '<style>' + css + '</style><layout><nav>ClickLab</nav><div class="app"><header id="top">Creator tools</header><main id="main">'
        html += '<div class="cw-video-grid">' + cards + '</div><div class="studio-workbench"><div class="card">Input</div><div class="card"><div class="studio-metrics vp-metrics">' + metrics + '</div></div></div></main></div></layout>'
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page()
            page.route('**/*', lambda route: route.abort())
            page.set_content(html)
            for width in [375, 768, 1024, 1144, 1366, 1440, 1920, 2560, 3840]:
                with self.subTest(width=width):
                    page.set_viewport_size({'width': width, 'height': 1080})
                    result = page.evaluate('''() => {
                        const main=document.querySelector('#main'),app=document.querySelector('.app');
                        const clipped=[...document.querySelectorAll('.studio-metric strong')].filter(e=>{
                            const range=document.createRange();range.selectNodeContents(e);
                            return range.getBoundingClientRect().width>e.clientWidth+1;
                        }).map(e=>e.textContent);
                        return {main:main.clientWidth,app:app.clientWidth,overflow:document.documentElement.scrollWidth>innerWidth,clipped,
                            card:document.querySelector('.cw-video-card').clientWidth,columns:getComputedStyle(document.querySelector('.cw-video-grid')).gridTemplateColumns.split(' ').length};
                    }''')
                    self.assertAlmostEqual(result['main'], result['app'], delta=1, msg=result)
                    self.assertFalse(result['overflow'], result)
                    self.assertEqual(result['clipped'], [], result)
                    if width >= 1920:
                        self.assertGreaterEqual(result['columns'], 4, result)
                        self.assertGreaterEqual(result['card'], 300, result)
            browser.close()


if __name__=='__main__':unittest.main()
