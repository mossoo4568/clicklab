"""Additional creator-tool workflows. Public measurements and explicit sample limits."""
import datetime as dt
import math
import re
import statistics
import html
import base64
import urllib.request
import urllib.parse


def read_artwork(url):
    def validate(value):
        u=urllib.parse.urlparse(value)
        if u.scheme!='https' or u.username or u.password or u.port not in (None,443) or not any(u.hostname==h or (u.hostname or '').endswith('.'+h) for h in ('ytimg.com','ggpht.com','googleusercontent.com')):
            raise ValueError('Artwork host is not an allowed YouTube image host.')
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validate(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    validate(url)
    with urllib.request.build_opener(Redirect).open(urllib.request.Request(url,headers={'User-Agent':'ClickLab/1.0'}),timeout=20) as response:
        content_type=response.headers.get_content_type()
        if content_type not in ('image/jpeg','image/png','image/webp','image/gif'):raise ValueError('Expected an image response.')
        body=response.read(12*1024*1024+1)
        if len(body)>12*1024*1024:raise ValueError('Artwork exceeds 12 MB download limit.')
    return content_type,base64.b64encode(body).decode('ascii')


def parse_vtt(text):
    cues=[]
    lines=str(text).replace('\r','').split('\n')
    for i,line in enumerate(lines):
        match=re.match(r'^\s*(\d+(?::\d{2}){1,2}[.,]\d+)\s+-->\s+(\d+(?::\d{2}){1,2}[.,]\d+)',line)
        if not match: continue
        body=[]
        for following in lines[i+1:]:
            if not following.strip(): break
            body.append(following)
        start,end=timestamp(match[1]),timestamp(match[2])
        content=html.unescape(re.sub(r'<[^>]*>','','\n'.join(body))).strip()
        if content and end>start:cues.append({'start':start,'end':end,'text':content})
    return cues


def rate(a, b):
    return round(a / b * 100, 3) if a is not None and b else None


def summary(rows, source_scope='Returned video sample; not an entire channel or historical index.'):
    """View-weighted rates use only available counts and positive view denominators."""
    def known(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0

    viewed = [v for v in rows if known(v.get('views'))]
    eligible = [v for v in viewed if v['views'] > 0]
    complete = [v for v in eligible if all(known(v.get(k)) for k in ('likes', 'comments'))]
    likes = [v for v in eligible if known(v.get('likes'))]
    comments = [v for v in eligible if known(v.get('comments'))]
    denominator = sum(v['views'] for v in complete)
    like_views = sum(v['views'] for v in likes)
    comment_views = sum(v['views'] for v in comments)
    times = []
    for v in rows:
        try:
            published = dt.datetime.fromisoformat(v.get('published', '').replace('Z', '+00:00'))
            times.append((published.replace(tzinfo=dt.timezone.utc) if published.tzinfo is None else published).astimezone(dt.timezone.utc))
        except (ValueError, TypeError, AttributeError):
            continue
    times.sort()
    span = (times[-1] - times[0]).total_seconds() / 86400 if len(times) > 1 else 0
    durations = [v['seconds'] for v in rows if known(v.get('seconds')) and v['seconds'] > 0]
    return {'sample': len(rows), 'source_scope': source_scope,
            'source_video_ids': [v['id'] for v in rows if v.get('id')],
            'views_known_videos': len(viewed), 'views_missing_videos': len(rows) - len(viewed),
            'median_views': statistics.median(v['views'] for v in viewed) if viewed else None,
            'like_rate': rate(sum(v['likes'] for v in likes), like_views),
            'comment_rate': rate(sum(v['comments'] for v in comments), comment_views),
            'engagement_rate': rate(sum(v['likes'] + v['comments'] for v in complete), denominator),
            'engagement_method': '100 × sum(likes + comments) / sum(views); complete counts and positive views only.',
            'engagement_denominator_views': denominator, 'complete_engagement_videos': len(complete),
            'engagement_excluded_videos': len(rows) - len(complete),
            'like_rate_videos': len(likes), 'like_rate_denominator_views': like_views,
            'comment_rate_videos': len(comments), 'comment_rate_denominator_views': comment_views,
            'dated_videos': len(times), 'published_from': times[0].isoformat() if times else None,
            'published_to': times[-1].isoformat() if times else None, 'observed_span_days': span if times else None,
            'uploads_per_week': round((len(times)-1)*7/span, 2) if span else None,
            'duration_known_videos': len(durations), 'duration_unknown_videos': len(rows) - len(durations),
            'short_duration_count': sum(seconds <= 180 for seconds in durations),
            'best_video': max(viewed, key=lambda v: v['views']) if viewed else None}


def tag_length(tags):
    return sum(len(t) + (2 if ' ' in t else 0) for t in tags) + max(0, len(tags)-1)


def timestamp(value):
    value = str(value).strip()
    if re.fullmatch(r'\d+(?:\.\d+)?', value): return float(value)
    if re.fullmatch(r'\d+(?::\d{1,2}){1,2}(?:[.,]\d+)?', value):
        parts = value.replace(',', '.').split(':')
        if any(float(p) >= 60 for p in parts[1:]): raise ValueError('Invalid minutes or seconds')
        n = 0
        for p in parts: n = n * 60 + float(p)
        return n
    if re.fullmatch(r'(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?', value) and value:
        return sum(int(n)*{'h':3600,'m':60,'s':1}[u] for n,u in re.findall(r'(\d+)([hms])',value))
    raise ValueError('Use seconds, m:ss, h:mm:ss or 1h2m3s')


def chapters(text, duration=None):
    rows=[]
    for line in str(text).splitlines():
        m=re.match(r'^\s*(\d+(?::\d{1,2}){1,2})\s+(.+?)\s*$',line)
        if m: rows.append({'seconds':timestamp(m[1]),'title':m[2]})
    checks=[('At least three chapters',len(rows)>=3),('Starts at 00:00',bool(rows) and rows[0]['seconds']==0),
            ('Ascending, at least 10 seconds apart',len(rows)>1 and all(b['seconds']-a['seconds']>=10 for a,b in zip(rows,rows[1:])))]
    checks.append(('Last chapter at least 10 seconds',duration-rows[-1]['seconds']>=10 if duration is not None and rows else None))
    return {'chapters':rows,'checks':checks,'valid':all(v is True for _,v in checks),
            'note':'Last chapter length cannot be verified without the video duration. Valid formatting does not guarantee YouTube chapter eligibility.'}


def run(s, kind, data):
    q=str(data.get('q','')).strip()
    result={'source':'YouTube Data API', 'fetched_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    if kind=='bulk-channel':
        inputs=list(dict.fromkeys(x.strip() for x in q.splitlines() if x.strip()))
        if not 1 <= len(inputs) <= 10: raise ValueError('Enter 1–10 channels, one per line.')
        rows=[]
        for value in inputs:
            try: rows.append({'input':value,**s.channel(value)})
            except ValueError as e: rows.append({'input':value,'error':str(e)})
        result.update(channels=rows, feature='bulk-channel')
    elif kind in ('engagement-live','compare-rich','outlier-live'):
        inputs=[x.strip() for x in q.splitlines() if x.strip()]
        if kind=='compare-rich' and not 2<=len(inputs)<=4: raise ValueError('Enter 2–4 channels.')
        profiles=[]
        for value in inputs[:4] if kind=='compare-rich' else inputs[:1]:
            vid=s.video_id(value)
            if vid and kind!='compare-rich':
                vs=s.videos([vid])
                if not vs: raise ValueError('Video unavailable.')
                v=vs[0];ch=s.channel(v['channel_id']);rows=s.uploads(ch,30)
                base=[x['views'] for x in rows if x['id']!=vid and x.get('views') is not None and (x['seconds']<=180)==(v['seconds']<=180)]
                m=statistics.median(base) if base else None
                sm=summary(vs if kind=='engagement-live' else rows)
                sm.update(video=v,baseline_n=len(base),baseline_views=m,multiplier=v['views']/m if m and v['views'] is not None else None)
            else: ch=s.channel(value);rows=s.uploads(ch,30);sm=summary(rows)
            profiles.append({'channel':ch,'summary':sm,'rows':rows})
        if not profiles: raise ValueError('Enter a video or channel URL.')
        result.update(feature=kind,profiles=profiles,note='Up to 30 recent uploads. Engagement is weighted by views and excludes missing counts. Upload cadence covers observed dates. Duration groups are not confirmed Shorts. Outlier baseline excludes the target; age differences remain.')
    elif kind=='image-download':
        variant=str(data.get('variant','high'))
        if data.get('asset') in ('avatar','banner'):
            ch=s.channel(q)
            url=ch.get('banner') if data['asset']=='banner' else ch.get('avatars',{}).get(variant,{}).get('url')
        else:
            vid=s.video_id(q)
            if not vid:raise ValueError('Enter a video URL.')
            vs=s.videos([vid])
            url=vs[0].get('thumbnails',{}).get(variant,{}).get('url') if vs else None
        if not url:raise ValueError('Requested artwork size is not available.')
        mime,payload=read_artwork(url)
        result.update(mime=mime,base64=payload)
    elif kind=='audit-rich':
        result=s.tool_run('channel-analysis',data)
        result['summary']=summary(result['rows'], 'Recent public uploads returned by channel analysis; not lifetime channel performance.')
        result['fixes']=[c['check'] for c in result['checks'] if not c['pass']][:3]
        result['note']+=' Top fixes are unmet checks, not predictions of growth.'
    elif kind=='handle-batch':
        handles=list(dict.fromkeys(re.findall(r'@[\w.-]{3,30}',q)))[:15]
        if not handles:raise ValueError('Paste candidate @handles to check.')
        found=[]
        for handle in handles:
            items=s.api('channels',part='snippet',forHandle=handle).get('items',[])
            found.append({'handle':handle,'status':'Public channel found' if items else 'No public match; claimability unknown','channel':items[0]['snippet']['title'] if items else None})
        result.update(handles=found,note='Up to 15 exact handles. An absent public result does not prove availability.')
    elif kind=='name-variants':
        handle=q.lstrip('@').replace(' ','')
        if not re.fullmatch(r'[\w.-]{3,30}',handle): raise ValueError('Enter a candidate handle with 3–30 letters, numbers, dots, underscores or hyphens.')
        variants=list(dict.fromkeys([handle]+[handle+x for x in ('TV','Official','HQ','Studio','Daily','Channel')]))
        rows=[]
        for name in variants:
            if len(name)>30: continue
            found=s.api('channels',part='snippet',forHandle='@'+name).get('items',[])
            rows.append({'handle':'@'+name,'status':'Public channel found' if found else 'No public match; registration availability unverified','channel':found[0]['snippet']['title'] if found else None,'id':found[0]['id'] if found else None})
        result.update(feature=kind,handles=rows,note='A missing public API match never proves a handle can be claimed.')
    elif kind=='comments-rich':
        vid=s.video_id(q)
        if not vid: raise ValueError('Enter a video URL.')
        vs=s.videos([vid]);owner=vs[0]['channel_id'] if vs else None
        p={'part':'snippet,replies','videoId':vid,'maxResults':100,'textFormat':'plainText','order':'relevance' if data.get('order')=='relevance' else 'time'}
        if data.get('search'):p['searchTerms']=str(data['search'])[:200]
        if data.get('page'):p['pageToken']=str(data['page'])
        r=s.api('commentThreads',**p);rows=[]
        def unpack(c,parent=None):
            sn=c['snippet'];return {'id':c['id'],'author':sn.get('authorDisplayName'),'author_id':sn.get('authorChannelId',{}).get('value'),
                'text':sn.get('textDisplay',''),'likes':sn.get('likeCount'),'published':sn.get('publishedAt'),'parent':parent}
        for thread in r.get('items',[]):
            row=unpack(thread['snippet']['topLevelComment']);replies=[unpack(c,row['id']) for c in thread.get('replies',{}).get('comments',[])]
            total=thread['snippet'].get('totalReplyCount',0)
            row.update(replies=total,loaded_replies=replies,replies_complete=len(replies)>=total,
                       owner_replied=True if any(c['author_id']==owner for c in replies) else (False if len(replies)>=total else None))
            rows.append(row)
        result.update(feature=kind,rows=rows,owner_id=owner,next_page=r.get('nextPageToken'),
                      note='Server-side searchTerms searches public top-level comments. Replies returned with threads may be incomplete; unknown creator-reply status stays unknown. Pagination expands coverage.')
    elif kind=='research-plus':
        if not q: raise ValueError('Enter a topic.')
        rows=s.search(q,str(data.get('region','US')),str(data.get('language','en')),days=int(data.get('days') or 0))
        phrases={}
        for v in rows:
            words=re.findall(r'[^\W_]+(?:[’\x27-][^\W_]+)*',v['title'].lower())
            seen=set(' '.join(words[i:i+n]) for n in (1,2,3,4) for i in range(len(words)-n+1))
            for phrase in seen:
                if len(phrase)<4:continue
                phrases.setdefault(phrase,[]).append(v)
        evidence=[]
        for phrase,vs in phrases.items():
            vals=[v['views'] for v in vs if v['views'] is not None]
            evidence.append({'phrase':phrase,'count':len(vs),'words':len(phrase.split()),'question':bool(re.match(r'^(how|why|what|when|where|can|is|are|does)\b',phrase)),
                'median_views':statistics.median(vals) if vals else None,'video_ids':[v['id'] for v in vs]})
        evidence.sort(key=lambda p:(p['count'],p['words']),reverse=True)
        result.update(feature=kind,rows=rows,phrases=evidence[:500],summary=summary(rows, 'Up to 50 live YouTube search results for the supplied query, region, language and date filter.'),
                      note='Phrase evidence from at most 50 live search results, not search volume or TubeMind’s historical index. No proprietary demand/opportunity score is fabricated.')
    elif kind=='rank-auto':
        vid=s.video_id(q)
        if not vid: raise ValueError('Enter a video URL.')
        vs=s.videos([vid])
        if not vs: raise ValueError('Video unavailable.')
        v=vs[0];keywords=[x.strip() for x in str(data.get('keywords','')).splitlines() if x.strip()]
        if not keywords: keywords=list(dict.fromkeys(v.get('tags',[])[:4]+[v['title']]))[:5]
        result=s.tool_run('rank',{**data,'keywords':'\n'.join(keywords)})
        result['auto_keywords']=keywords
    elif kind=='trending-filtered':
        params={'part':'id','chart':'mostPopular','regionCode':str(data.get('region','US')).upper(),'maxResults':50}
        if data.get('category'):params['videoCategoryId']=str(data['category'])
        r=s.api('videos',**params);result['rows']=s.videos([v['id'] for v in r.get('items',[])])
    else: raise ValueError('Unknown extended action.')
    return result
