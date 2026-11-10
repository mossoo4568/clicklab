import ast
import datetime as dt
import json
import re
import shutil
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import studio_backend as s


class TrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        s.configure(SimpleNamespace(OUT=Path(self.tmp.name)))

    def tearDown(self):
        self.tmp.cleanup()

    def test_boundaries_missing_and_real_zero(self):
        rows=[{'at':10000,'data':{'views':100}}, {'at':13600,'data':{'views':100}}]
        self.assertEqual(s.delta(rows,3600)['value'],0)
        self.assertIsNone(s.delta(rows,86400)['value'])
        self.assertIsNone(s.delta(rows[:1],3600)['value'])

    def test_negative_corrections_are_preserved(self):
        rows=[{'at':0,'data':{'views':100}}, {'at':3600,'data':{'views':91}}]
        self.assertEqual(s.delta(rows,3600)['value'],-9)

    def test_unknown_metric_not_zero(self):
        rows=[{'at':0,'data':{'views':None}}, {'at':3600,'data':{'views':91}}]
        self.assertIsNone(s.delta(rows,3600)['value'])

    def test_wide_gap_cannot_be_one_hour_gain(self):
        rows=[{'at':0,'data':{'views':100}}, {'at':7200,'data':{'views':200}}]
        self.assertIsNone(s.delta(rows,3600)['value'])

    def test_persistence_ledger_and_csv(self):
        cid='UCabcdefghijklmnopqrstuv';now=time.time()
        with s.db() as con:
            con.execute('INSERT INTO tracked(id,name,interval) VALUES(?,?,?)',(cid,'Test',3600))
            for at,views in [(now-86400,100),(now-3600,170),(now,200)]:
                d={'id':cid,'name':'Test','views':views,'subscribers':None,'videos':2,'source':'fixture',
                   'fetched_at':dt.datetime.fromtimestamp(at,dt.timezone.utc).isoformat(),
                   'collection_interval':3600,'gap_from_previous':views==170}
                con.execute('INSERT INTO observations VALUES(?,?,?)',(cid,at,json.dumps(d)))
        r=s.report(cid)
        self.assertEqual(r['changes']['24h']['value'],100)
        self.assertEqual(r['changes']['1h']['value'],30)
        self.assertTrue(r['intervals'][0]['gap'])
        self.assertEqual(r['readings'],3)
        self.assertEqual(len(r['hourly']),24)
        self.assertEqual(r['hourly'][-1]['value'],30)
        self.assertIsNone(r['hourly'][0]['value'])
        with s.db() as con:
            con.execute('UPDATE tracked SET interval=86400 WHERE id=?',(cid,))
        # Historical gaps are immutable when the future schedule changes.
        self.assertTrue(s.report(cid)['intervals'][0]['gap'])
        # No worker needed for this pure export check.
        old=s.STARTED;s.STARTED=True
        try:
            exported=s.tracker('export',{'id':cid})['csv']
            self.assertIn('subscribers_public_rounded',exported)
            self.assertEqual(len(exported.splitlines()),4)
        finally:s.STARTED=old

    def test_url_parsing_rejects_unrelated_domains(self):
        self.assertEqual(s.video_id('https://youtu.be/dQw4w9WgXcQ?t=1'),'dQw4w9WgXcQ')
        self.assertEqual(s.video_id('https://www.youtube.com/shorts/dQw4w9WgXcQ'),'dQw4w9WgXcQ')
        self.assertIsNone(s.video_id('https://example.com/watch?v=dQw4w9WgXcQ'))
        with self.assertRaises(ValueError):s.channel('https://example.com/@mkbhd')

    def test_api_errors_redact_key(self):
        s.HOST.yt_get=lambda *args:{'error':'failed https://api.example/?key=secret&part=snippet'}
        with self.assertRaisesRegex(ValueError,r'key=\[redacted\]') as e:s.api('channels')
        self.assertNotIn('secret',str(e.exception))

    def test_old_paused_channel_stays_visible(self):
        cid='UCabcdefghijklmnopqrstuv';at=time.time()-40*86400
        with s.db() as con:
            con.execute('INSERT INTO tracked(id,name,interval,enabled) VALUES(?,?,?,0)',(cid,'Paused',3600))
            con.execute('INSERT INTO observations VALUES(?,?,?)',(cid,at,json.dumps({'id':cid,'views':12})))
        self.assertEqual(s.report(cid)['channel']['views'],12)
        self.assertEqual(len(s.watchlist()),1)

    def test_playlist_duplicate_occurrences_preserved(self):
        s.HOST._iso_dur=lambda value:60
        s.HOST.yt_get=lambda *args:{'items':[{'id':'abcdefghijk','snippet':{'publishedAt':'2026-01-01T00:00:00Z'},'statistics':{'viewCount':'0'},'contentDetails':{'duration':'PT1M'}}]}
        rows=s.videos(['abcdefghijk','abcdefghijk'])
        self.assertEqual(len(rows),2)
        self.assertEqual(sum(r['seconds'] for r in rows),120)
        self.assertEqual(rows[0]['views'],0)
        self.assertIsNone(rows[0]['likes'])

    def test_recent_id_refresh_reuses_record_without_api(self):
        cid='UCabcdefghijklmnopqrstuv';at=time.time()
        with s.db() as con:
            con.execute('INSERT INTO tracked(id,name,interval) VALUES(?,?,?)',(cid,'Recent',3600))
            con.execute('INSERT INTO observations VALUES(?,?,?)',(cid,at,json.dumps({'id':cid,'views':12})))
        def fail(*args):raise AssertionError('Duplicate refresh should not call API')
        s.HOST.yt_get=fail
        self.assertEqual(s.observe(cid)['channel']['views'],12)

    def test_settings_returns_status_without_credentials(self):
        secret='test-private-credential'
        s.HOST.yt_key=lambda:secret
        s.HOST.yt_keys=lambda:[secret]
        s.HOST.gem_key=lambda:secret
        s.HOST.gem_keys=lambda:[secret]
        s.HOST.rw_key=lambda:secret
        s.HOST.GEM_MODEL='test-model'
        s.HOST.AIM={'test':{'name':'Test model'}}
        s.HOST.AIDEF='test'
        s.HOST.OCR_GEM=False
        s.HOST.eng_state=lambda:{'ocr':True}
        result=s.tool_run('settings',{})
        self.assertNotIn(secret,json.dumps(result))
        self.assertTrue(result['providers']['youtube']['configured'])
        self.assertEqual(result['providers']['youtube']['keys'],1)
        self.assertFalse(result['ocr_cloud'])

    def test_multiple_channels_are_isolated(self):
        with s.db() as con:
            for cid,views in [('UCabcdefghijklmnopqrstuv',11),('UCzyxwvutsrqponmlkjihgfe',22)]:
                con.execute('INSERT INTO tracked(id,name,interval) VALUES(?,?,?)',(cid,cid,3600))
                con.execute('INSERT INTO observations VALUES(?,?,?)',(cid,time.time(),json.dumps({'id':cid,'views':views})))
        self.assertEqual(len(s.watchlist()),2)
        self.assertEqual(s.report('UCabcdefghijklmnopqrstuv')['channel']['views'],11)
        self.assertEqual(s.report('UCzyxwvutsrqponmlkjihgfe')['channel']['views'],22)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.previous_host = s.HOST
        s.configure(SimpleNamespace(OUT=Path(self.tmp.name)))

    def tearDown(self):
        s.configure(self.previous_host)
        self.tmp.cleanup()

    def create(self, name='Planned channel'):
        return s.workspace('create', {'name': name, 'niche': 'Education', 'country': 'PK', 'language': 'ur'})['workspace']

    def public_channel(self, cid):
        return {'id': cid, 'name': cid, 'views': 100, 'subscribers': None, 'videos': 5,
                'recent_videos': [], 'fetched_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'source': 'Fixture'}

    def add(self, wid, cid, relation='direct'):
        ch = self.public_channel(cid)
        with patch.object(s, 'channel', return_value=ch), patch.object(s, 'observe', return_value={'channel': ch}):
            return s.workspace('add-competitor', {'id': wid, 'q': cid, 'relation': relation})['workspace']

    def test_planned_channels_work_without_any_api(self):
        a, b = self.create('First'), self.create('Second')
        self.assertNotEqual(a['id'], b['id'])
        self.assertIsNone(a['channel'])
        self.assertEqual(len(s.workspace_list()['channels']), 2)
        self.assertEqual(s.workspace_compare({'id': a['id']})['profiles'], [])

    def test_ten_competitors_per_channel_not_globally(self):
        a, b = self.create('First'), self.create('Second')
        for i in range(10):
            self.add(a['id'], 'UC' + str(i).zfill(22))
            self.add(b['id'], 'UC' + str(i).zfill(22), 'format')
        self.assertEqual([x['competitor_count'] for x in s.workspace_list()['channels']], [10, 10])
        with patch.object(s, 'channel', side_effect=AssertionError('Limit must be checked before API')):
            with self.assertRaisesRegex(ValueError, '10 competitors'):
                s.workspace('add-competitor', {'id': a['id'], 'q': '@extra'})
        s.workspace('remove-competitor', {'id': a['id'], 'competitor_id': 'UC' + '0'.zfill(22)})
        self.assertEqual([x['competitor_count'] for x in s.workspace_list()['channels']], [9, 10])

    def test_duplicates_and_self_are_rejected(self):
        own = self.create()
        cid = 'UC' + '1'.zfill(22)
        self.add(own['id'], cid)
        with self.assertRaisesRegex(ValueError, 'already saved'):
            self.add(own['id'], cid)
        with s.db() as con:
            con.execute('UPDATE workspaces SET youtube_id=? WHERE id=?', ('UC' + '2'.zfill(22), own['id']))
        with self.assertRaisesRegex(ValueError, 'own competitor'):
            self.add(own['id'], 'UC' + '2'.zfill(22))

    def test_invalid_metadata_and_mapping_do_not_write(self):
        with self.assertRaises(ValueError): self.create('')
        with self.assertRaises(ValueError): s.workspace('create', {'name': 'Test', 'country': 'Pakistan'})
        own = self.create()
        with self.assertRaises(ValueError): self.add(own['id'], 'a', 'invented')
        with self.assertRaises(ValueError): self.add('unknown', 'a')
        self.assertEqual(s.workspace_list()['channels'][0]['competitor_count'], 0)

    def test_comparison_preserves_unknown_metrics_and_zero(self):
        own = self.create()
        self.add(own['id'], 'UC' + '1'.zfill(22))
        result = s.workspace_compare({'id': own['id']})
        p = result['profiles'][0]
        self.assertEqual(p['channel']['views'], 100)
        self.assertIsNone(p['channel']['subscribers'])
        self.assertIsNone(p['summary']['engagement_rate'])
        self.assertIsNone(p['summary']['median_views'])
        self.assertIsNone(p['changes']['24h']['value'])
        self.assertTrue(result['warnings'])

    def test_latest_observation_updates_all_workspace_references(self):
        own = self.create()
        cid = 'UC' + '1'.zfill(22)
        self.add(own['id'], cid)
        ch = self.public_channel(cid)
        ch['views'] = 200
        with s.db() as con:
            con.execute('INSERT INTO observations VALUES(?,?,?)', (cid, time.time(), json.dumps(ch)))
        self.assertEqual(s.workspace_list()['channels'][0]['competitors'][0]['channel']['views'], 200)

    def test_outlier_requires_three_age_and_duration_matched_references(self):
        rows = [{'id': str(i), 'views': views, 'seconds': 300, 'age_days': 10}
                for i, views in enumerate([1000, 100, 200, 300])]
        result = s.sampled_video(rows[0], rows)
        self.assertEqual(result['baseline_n'], 3)
        self.assertEqual(result['baseline_views'], 200)
        self.assertEqual(result['multiplier'], 5)
        rows[1]['age_days'] = 100
        self.assertIsNone(s.sampled_video(rows[0], rows)['multiplier'])
        rows[1]['age_days'] = 10
        rows[1]['seconds'] = 90
        self.assertIsNone(s.sampled_video(rows[0], rows)['multiplier'])
        rows[1]['seconds'] = 300
        rows[1]['views'] = None
        self.assertIsNone(s.sampled_video(rows[0], rows)['multiplier'])

    def test_publication_and_duration_filters_do_not_change_totals(self):
        now = dt.datetime.now(dt.timezone.utc)
        ch = self.public_channel('UC' + '1'.zfill(22))
        ch['recent_videos'] = [{'id': 'a', 'views': 0, 'likes': 0, 'comments': 0,
                               'seconds': 90, 'published': now.isoformat(), 'age_days': 1, 'views_per_day': 0},
                              {'id': 'b', 'views': 80, 'likes': None, 'comments': 1,
                               'seconds': 300, 'published': (now-dt.timedelta(days=40)).isoformat(),
                               'age_days': 40, 'views_per_day': 2}]
        result = s.comparison_profile(ch, 'direct', 7, 'short-duration')
        self.assertEqual(result['channel']['views'], 100)
        self.assertEqual(result['summary']['sample'], 1)
        self.assertEqual(result['summary']['median_views'], 0)
        self.assertIsNone(result['summary']['engagement_rate'])
        self.assertEqual(result['summary']['median_views_per_day'], 0)

    def test_refresh_failure_preserves_saved_data(self):
        own = self.create()
        self.add(own['id'], 'UC' + '1'.zfill(22))
        with patch.object(s, 'observe', side_effect=ValueError('Provider temporarily unavailable')):
            result = s.workspace_compare({'id': own['id'], 'refresh': True})
        self.assertEqual(result['profiles'][0]['channel']['views'], 100)
        self.assertIn('saved data preserved', ' '.join(result['warnings']))

    def test_local_ocr_gateway_never_selects_cloud(self):
        s.HOST.shutil = SimpleNamespace(which=lambda name: 'ffmpeg')
        s.HOST.load_ocr = lambda: None
        s.HOST.find_tesseract = lambda: 'tesseract'
        calls = []
        s.HOST.tr_ocr = lambda vid, local_only=False: calls.append(local_only) or {'text': '00:00 Screen text'}
        result = s.source_context({'q': 'dQw4w9WgXcQ', 'method': 'ocr'})
        self.assertEqual(calls, [True])
        self.assertEqual(result['kind'], 'ocr')
        self.assertIn('not speech', result['source'])
        self.assertFalse(s.SOURCE_JOBS)

    def test_source_subtitles_preserve_timing_and_release_failed_jobs(self):
        s.HOST.tr_get = lambda vid: {'text': 'Words', 'cues': [{'start': 1.25, 'end': 4, 'text': 'Words'}]}
        result = s.source_context({'q': 'dQw4w9WgXcQ'})
        self.assertEqual(result['cues'][0]['start'], 1.25)
        self.assertEqual(result['timed_text'], '00:00:01  Words')
        s.HOST.tr_get = lambda vid: {'error': 'No subtitles'}
        with self.assertRaisesRegex(ValueError, 'No subtitles'):
            s.source_context({'q': 'dQw4w9WgXcQ'})
        self.assertFalse(s.SOURCE_JOBS)


class OcrEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vid = 'abcdefghijk'
        self.calls = []

        def run(cmd, timeout):
            if cmd[0] == 'yt-dlp':
                Path(cmd[cmd.index('-o') + 1].replace('%(ext)s', 'mp4')).write_bytes(b'fixture')
            elif cmd[0] == 'ffmpeg':
                Path(cmd[-1].replace('%04d', '0001')).write_bytes(b'fixture')
            return 0, '12', ''

        def local(path, gem_ok=None):
            self.calls.append(('local', gem_ok))
            return [{'t': 'Local screen text', 'x': 0, 'y': 0}]

        def api(path):
            self.calls.append(('api', None))
            return [{'t': 'API screen text', 'x': 0, 'y': 0}]

        path = Path(__file__).with_name('clicklab.py')
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'tr_ocr')
        self.env = {'re': re, 'TR_DIR': self.root, 'Image': object(), '_TRP': {},
                    'shutil': SimpleNamespace(which=lambda n: n, rmtree=shutil.rmtree),
                    'find_ytdlp': lambda: 'yt-dlp', 'run': run, '_log': lambda *a: None,
                    'ocr_words': local, 'gem_ocr': api, 'gem_keys': lambda: ['fixture-key']}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), self.env)

    def test_api_does_not_relabel_auto_or_local_cache(self):
        (self.root / (self.vid + '.ocr.txt')).write_text('Legacy mixed engine cache', encoding='utf-8')
        (self.root / (self.vid + '.local.ocr.txt')).write_text('Local cache', encoding='utf-8')
        result = self.env['tr_ocr'](self.vid, force_gem=True)
        self.assertEqual(self.calls, [('api', None)])
        self.assertIn('API screen text', result['text'])
        self.assertEqual(result['engine'], 'api')
        self.assertTrue((self.root / (self.vid + '.api.ocr.txt')).exists())
        self.calls.clear()
        cached = self.env['tr_ocr'](self.vid, force_gem=True)
        self.assertTrue(cached['cached'])
        self.assertEqual(cached['engine'], 'api')
        self.assertEqual(self.calls, [])

    def test_api_failure_never_falls_back_or_caches_local_text(self):
        self.env['gem_ocr'] = lambda *a: None
        result = self.env['tr_ocr'](self.vid, force_gem=True)
        self.assertIn('error', result)
        self.assertIn('API', result['error'])
        self.assertEqual(self.calls, [])
        self.assertFalse(list(self.root.glob('*.ocr.txt')))
        self.assertFalse(self.env['_TRP'])

    def test_local_never_calls_api(self):
        result = self.env['tr_ocr'](self.vid, local_only=True)
        self.assertEqual(self.calls, [('local', False)])
        self.assertEqual(result['engine'], 'local')
        self.assertIn('Local screen text', result['text'])

    def test_api_gateway_requires_key_and_preserves_job_cleanup(self):
        host = SimpleNamespace(shutil=SimpleNamespace(which=lambda n: n), gem_keys=lambda: [])
        with patch.object(s, 'HOST', host):
            with self.assertRaisesRegex(ValueError, 'Gemini key'):
                s.source_context({'q': self.vid, 'method': 'ocr', 'engine': 'api'})
            with self.assertRaisesRegex(ValueError, 'Choose local or API'):
                s.source_context({'q': self.vid, 'method': 'ocr', 'engine': 'invalid'})
        self.assertFalse(s.SOURCE_JOBS)

    def test_api_gateway_does_not_require_local_ocr_engine(self):
        calls = []
        host = SimpleNamespace(shutil=SimpleNamespace(which=lambda n: n), gem_keys=lambda: ['fixture-key'],
                               tr_ocr=lambda vid, **kw: calls.append(kw) or {'text': 'API text', 'engine': 'api'})
        with patch.object(s, 'HOST', host):
            result = s.source_context({'q': self.vid, 'method': 'ocr', 'engine': 'api'})
        self.assertEqual(calls, [{'local_only': False, 'force_gem': True}])
        self.assertIn('API', result['source'])
        self.assertEqual(result['engine'], 'api')
        self.assertFalse(s.SOURCE_JOBS)

    def test_video_metadata_remains_verbatim_and_complete(self):
        description = '  Intro & <text>\r\n' + 'Full description line\n' * 200 + 'LAST LINE  '
        tags = ['Whole phrase', 'CaseSensitive', 'اردو', 'tag, with comma'] + ['tag' + str(i) for i in range(60)]
        host = SimpleNamespace(_iso_dur=lambda value: 60, yt_get=lambda *a: {'items': [
            {'id': self.vid, 'snippet': {'title': 'Title', 'description': description, 'tags': tags, 'publishedAt': '2026-01-01T00:00:00Z'},
             'contentDetails': {'duration': 'PT1M'}, 'statistics': {}}]})
        with patch.object(s, 'HOST', host):
            result = s.videos([self.vid])[0]
        self.assertEqual(result['description'], description)
        self.assertEqual(result['tags'], tags)


class LegacyMetadataTests(unittest.TestCase):
    def setUp(self):
        import hashlib
        from collections import Counter
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.vid = 'abcdefghijk'
        self.description = '\n  Original\r\n' + 'Full description\n' * 300 + 'LAST LINE  '
        self.tags = ['  Original spelling  ', 'two, words'] + ['Tag ' + str(i) for i in range(62)]
        self.metadata = {'title': 'Unapplied title words', 'ch': 'Creator', 'tags': self.tags, 'desc': self.description}
        self.env = {'re': re, 'json': json, 'dt': dt, 'hashlib': hashlib, 'Counter': Counter,
                    'toks': lambda value: value.lower().split(), 'META_DIR': self.root,
                    'IDEA_DIR': self.root / 'ideas', 'gem_key': lambda: None,
                    'find_ytdlp': lambda: 'fixture-downloader'}
        path = Path(__file__).with_name('clicklab.py')
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('meta_of', 'idea_pack')]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), self.env)

    def test_legacy_metadata_replaces_truncated_cache_and_keeps_verbatim_values(self):
        cache = self.root / (self.vid + '.json')
        cache.write_text(json.dumps({'v': 3, 'tags': self.tags[:40], 'desc': self.description[:4000]}), encoding='utf-8')
        payload = {'title': 'Title', 'tags': self.tags, 'description': self.description}
        calls = []
        self.env['run'] = lambda *a, **kw: calls.append(a) or (0, json.dumps(payload), '')
        result = self.env['meta_of'](self.vid)
        self.assertEqual(result['tags'], self.tags)
        self.assertEqual(result['desc'], self.description)
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.env['meta_of'](self.vid), result)
        self.assertEqual(len(calls), 1)

    def test_idea_packet_keywords_are_all_applied_tags_not_tokens(self):
        self.env['meta_of'] = lambda vid: self.metadata
        result = self.env['idea_pack'](self.vid)
        self.assertEqual(result['tags'], self.tags)
        self.assertEqual(result['keywords'], self.tags)
        self.assertNotIn('unapplied', result['keywords'])

    def test_cached_ideas_cannot_restore_old_guessed_keywords(self):
        self.metadata['tags'] = ['Original TAG', 'two, words']
        self.env['meta_of'] = lambda vid: self.metadata
        self.env['gem_key'] = lambda: 'fixture-key'
        self.env['llm_txt'] = lambda *a, **kw: self.fail('A cached idea must not call an AI provider')
        context = ('VIDEO TITLE: ' + self.metadata['title'] + '\nCHANNEL: Creator\nASLI TAGS: ' +
                   ', '.join(self.metadata['tags']) + '\nDESCRIPTION (excerpt): ' +
                   re.sub(r'\s+', ' ', self.description)[:1200])
        folder = self.env['IDEA_DIR']
        folder.mkdir()
        (folder / (self.vid + '.json')).write_text(json.dumps({
            'ok': True, 'tags': ['stale'], 'keywords': ['guessed'], 'ideas': [{'t': 'Saved draft'}],
            'ctx_h': self.env['hashlib'].md5(context.encode('utf-8')).hexdigest()}), encoding='utf-8')
        result = self.env['idea_pack'](self.vid)
        self.assertTrue(result['cached'])
        self.assertEqual(result['tags'], self.metadata['tags'])
        self.assertEqual(result['keywords'], self.metadata['tags'])
        self.assertEqual(result['ideas'], [{'t': 'Saved draft'}])


if __name__=='__main__':unittest.main()
