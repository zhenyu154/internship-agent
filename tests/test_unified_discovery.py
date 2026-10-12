# Public copy: synthetic identities and timestamps; no live source verification.
"""Offline mixed-source discovery, pagination, recovery and preservation tests."""

from dataclasses import replace
from io import StringIO
import contextlib
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import yaml

from internship_agent.config import ConfigurationError, load_config
from internship_agent.database import JobDatabase, RunStateError, SCHEMA_VERSION
from internship_agent.greenhouse import GreenhouseBoard, GreenhouseClient, GreenhouseDataError
from internship_agent.lever import LeverClient, LeverDataError
from internship_agent.models import Job
from internship_agent.unified_discovery import UnifiedDiscovery, normalize_posting, exclusive_run_lock
from internship_agent.unified_report import write_unified_report

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/search_preferences.example.yaml'


def raw(key, title='Machine Learning Intern', description='Summer 2027 internship. Train models and evaluate policies.', **kwargs):
    values=dict(title=title,description=description,source_job_id=key,posting_id=key,
                location='San Francisco, CA',application_url=f'https://jobs.example.test/{key}/apply',
                hosted_url=f'https://jobs.example.test/{key}',job_url=f'https://jobs.example.test/{key}',
                apply_url=f'https://jobs.example.test/{key}/apply',verified_at='2025-01-10T00:00:00Z',
                published_at='UNKNOWN',updated_at='2025-01-08T00:00:00Z',is_listed=True)
    return SimpleNamespace(**{**values,**kwargs})


class FakeGreenhouse:
    def __init__(self,jobs=None): self.jobs=jobs if jobs is not None else [raw('gh-1')];self.calls=[]
    def fetch_jobs(self,board):
        self.calls.append(board.board_token)
        if isinstance(self.jobs,Exception):raise self.jobs
        return self.jobs


class FakeAshby:
    def __init__(self,jobs=None):self.jobs=jobs if jobs is not None else [raw('a-1')];self.calls=[]
    def fetch_board(self,token):
        self.calls.append(token)
        if isinstance(self.jobs,Exception):raise self.jobs
        return self.jobs


class FakeLever:
    page_limit=100
    def __init__(self,pages=None,fail_offset=None):
        self.pages=pages if pages is not None else [[raw('l-1')]]
        self.fail_offset=fail_offset;self.calls=[]
    def iter_site_pages(self,record,start_skip=0):
        self.calls.append(start_skip)
        for index in range(start_skip//100,len(self.pages)):
            offset=index*100
            if offset==self.fail_offset:raise LeverDataError('simulated page timeout')
            yield f'{record.site_token}:{offset}',self.pages[index]


class UnifiedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config_dir=self.root/'config';self.config_dir.mkdir()
        self.db=self.root/'jobs.sqlite3'
        self.specs=[('greenhouse_boards.yaml','boards','board_token','g-board'),
                    ('lever_sites.yaml','sites','site_token','l-site'),
                    ('ashby_boards.yaml','boards','board_name','a-board')]
        for filename,collection,field,token in self.specs:
            host='https://boards.greenhouse.io' if field=='board_token' else 'https://jobs.lever.co' if field=='site_token' else 'https://jobs.ashbyhq.com'
            data={'version':1,collection:[{'company_name':f'Example {token}',field:token,
                'source_url':f'{host}/{token}','active':True,'verified_at':'2025-01-10T00:00:00Z'}]}
            (self.config_dir/filename).write_text(yaml.safe_dump(data),encoding='utf-8')
        self.clients={'greenhouse':FakeGreenhouse(),'lever':FakeLever(),'ashby':FakeAshby()}

    def service(self):return UnifiedDiscovery(clients=self.clients)
    def run_service(self,**kwargs):
        return self.service().run(CONFIG,self.config_dir,database_path=self.db,limit=2,**kwargs)

    def test_all_three_adapters_are_invoked_and_company_is_registry_owned(self):
        result=self.run_service()
        self.assertEqual(len(result.coverage),3)
        self.assertEqual([c.status for c in result.coverage],['COMPLETED']*3)
        self.assertEqual({j.source for j in result.all_jobs},{'greenhouse','lever','ashby'})
        self.assertEqual(result.all_jobs[0].company_name,'Example g-board')
        self.assertEqual(self.clients['lever'].calls,[0])

    def test_registry_expansion_is_reflected_without_hardcoded_names(self):
        p=self.config_dir/'greenhouse_boards.yaml';d=yaml.safe_load(p.read_text())
        d['boards'].append({**d['boards'][0],'board_token':'new-board','company_name':'Another Example','source_url':'https://boards.greenhouse.io/new-board'})
        p.write_text(yaml.safe_dump(d))
        self.assertEqual(len(self.run_service().coverage),4)
        self.assertIn('new-board',self.clients['greenhouse'].calls)

    def test_inactive_and_unverified_boards_are_skipped(self):
        p=self.config_dir/'greenhouse_boards.yaml';d=yaml.safe_load(p.read_text());d['boards'][0]['active']=False;p.write_text(yaml.safe_dump(d))
        p=self.config_dir/'lever_sites.yaml';d=yaml.safe_load(p.read_text());d['sites'][0]['verified_at']='UNKNOWN';p.write_text(yaml.safe_dump(d))
        self.assertEqual(len(self.run_service().coverage),1)
        self.assertFalse(self.clients['greenhouse'].calls)
        self.assertFalse(self.clients['lever'].calls)

    def test_source_and_board_selection(self):
        result=self.run_service(sources=['lever'],boards=['lever:l-site'])
        self.assertEqual(len(result.coverage),1)
        with self.assertRaises(ConfigurationError):self.run_service(boards=['ashby:missing'])

    def test_all_lever_pages_are_scanned_past_100_even_with_preview_limit(self):
        self.clients['lever']=FakeLever([[raw(f'l-{i}') for i in range(100)],[raw('late',title='Robot Learning Intern',description='Train learned manipulation policies.')]])
        result=self.run_service(sources=['lever'])
        self.assertEqual(result.coverage[0].raw_jobs,101)
        self.assertEqual(result.coverage[0].pages,2)
        self.assertEqual(result.coverage[0].status,'COMPLETED')
        self.assertEqual(result.preview[0].posting_id,'late')

    def test_exact_full_lever_page_needs_terminal_empty_page(self):
        self.clients['lever']=FakeLever([[raw(f'l-{i}') for i in range(100)],[]])
        result=self.run_service(sources=['lever'])
        self.assertEqual(result.coverage[0].raw_jobs,100)
        self.assertEqual(result.coverage[0].pages,2)
        self.assertEqual(result.coverage[0].status,'COMPLETED')

    def test_stopping_before_terminal_page_is_incomplete(self):
        self.clients['lever']=FakeLever([[raw(f'l-{i}') for i in range(100)]])
        result=self.run_service(sources=['lever'])
        self.assertEqual(result.coverage[0].status,'INCOMPLETE')
        self.assertIn('terminal',result.coverage[0].error)

    def test_repeated_page_loop_is_incomplete(self):
        page=[raw(f'l-{i}') for i in range(100)]
        self.clients['lever']=FakeLever([page,page,page])
        result=self.run_service(sources=['lever'])
        self.assertEqual(result.coverage[0].status,'INCOMPLETE')
        self.assertEqual(result.coverage[0].pages,1)
        self.assertIn('Repeated',result.coverage[0].error)

    def test_missing_posting_identity_marks_board_incomplete(self):
        self.clients['greenhouse']=FakeGreenhouse([raw('UNKNOWN')])
        result=self.run_service()
        self.assertEqual(result.coverage[0].status,'INCOMPLETE')
        self.assertEqual(result.coverage[1].status,'COMPLETED')

    def test_one_failed_board_does_not_block_other_sources(self):
        self.clients['greenhouse']=FakeGreenhouse(GreenhouseDataError('malformed response'))
        result=self.run_service(save=True,save_all=True)
        self.assertEqual(result.newly_saved,2)
        self.assertEqual(sum(c.status=='COMPLETED' for c in result.coverage),2)
        with JobDatabase(self.db) as database:self.assertEqual(database.get_run(result.run_id).status,'INTERRUPTED')

    def test_ashby_unlisted_posting_is_excluded(self):
        self.clients['ashby']=FakeAshby([raw('hidden',is_listed=False)])
        result=self.run_service(sources=['ashby'])
        self.assertEqual(result.counts,{'EXCLUDED':1})
        self.assertEqual(result.preview,[])

    def test_unknown_ashby_listing_status_requires_review(self):
        self.clients['ashby']=FakeAshby([raw('unknown',is_listed=None)])
        self.assertEqual(self.run_service(sources=['ashby']).all_jobs[0].relevance_category,'NEEDS_REVIEW')

    def test_unknown_authorization_does_not_hide_high_value_role(self):
        self.clients['ashby']=FakeAshby([raw('manip',title='Robotics Software Internship, Manipulation',description='Implement manipulation algorithms. Cohort dates require review.')])
        result=self.run_service()
        self.assertEqual(result.preview[0].posting_id,'manip')
        self.assertEqual(result.preview[0].work_authorization,'UNKNOWN')
        self.assertEqual(result.preview[0].relevance_category,'NEEDS_REVIEW')

    def test_generic_2027_internship_is_not_assumed_summer(self):
        self.clients['ashby']=FakeAshby([raw('generic',title='2027 Machine Learning Intern',description='Train models in PyTorch.')])
        result=self.run_service(sources=['ashby'])
        self.assertEqual(result.all_jobs[0].internship_term,'UNKNOWN')
        self.assertEqual(result.all_jobs[0].relevance_category,'NEEDS_REVIEW')

    def test_graduation_summer_date_is_not_internship_term(self):
        self.clients['ashby']=FakeAshby([raw('grad',description='Train models. Candidates must be graduating Summer 2027.')])
        self.assertEqual(self.run_service(sources=['ashby']).all_jobs[0].internship_term,'UNKNOWN')

    def test_explicit_wrong_internship_term_is_excluded(self):
        self.clients['ashby']=FakeAshby([raw('wrong',title='Machine Learning Intern - Summer 2026',description='Summer 2026 internship training policies.')])
        self.assertEqual(self.run_service(sources=['ashby']).counts,{'EXCLUDED':1})

    def test_spring_coop_with_separated_start_year_is_excluded(self):
        self.clients['lever']=FakeLever([[raw('spring',title='Electrical Engineering Spring Co-op (January 2027)',description='Academic-year co-op. Ideal start is January 2027; end date flexible.')]])
        job=self.run_service(sources=['lever']).all_jobs[0]
        self.assertEqual(job.relevance_category,'EXCLUDED')
        self.assertIn('Spring 2027',job.relevance_reason)

    def test_phd_only_is_excluded_but_masters_or_phd_is_not(self):
        self.clients['ashby']=FakeAshby([
            raw('phd',description='Summer 2027 internship. PhD degree required.'),
            raw('masters',description="Summer 2027 internship. Master's or PhD degree in CS accepted."),
        ])
        result=self.run_service(sources=['ashby'])
        states={j.posting_id:j.relevance_category for j in result.all_jobs}
        self.assertEqual(states['phd'],'EXCLUDED');self.assertNotEqual(states['masters'],'EXCLUDED')

    def test_labeled_program_cohort_confirms_summer_without_using_graduation(self):
        self.clients['ashby']=FakeAshby([raw('cohort',description='Program dates:\nWinter 2027: January-April\nSummer 2027: Late May-September\nTrain models.')])
        job=self.run_service(sources=['ashby']).all_jobs[0]
        self.assertEqual(job.internship_term,'Summer 2027')

    def test_sponsored_social_events_are_not_work_authorization(self):
        self.clients['ashby']=FakeAshby([raw('social',description='Summer 2027 internship. Train models. Join company sponsored events.')])
        self.assertEqual(self.run_service(sources=['ashby']).all_jobs[0].work_authorization,'UNKNOWN')

    def test_mechanical_design_is_hardware_review_not_main_shortlist(self):
        self.clients['lever']=FakeLever([[raw('mech',title='Summer 2027 Mechanical Engineering Intern',description='Design mechanical test stands and fixtures. CAD tools preferred.')]])
        job=self.run_service(sources=['lever']).all_jobs[0]
        from internship_agent.relevance import preview_priority
        self.assertEqual(job.relevance_category,'NEEDS_REVIEW')
        self.assertEqual(preview_priority(job)[0],4)

    def test_product_design_with_ai_portfolio_is_not_engineering(self):
        self.clients['greenhouse']=FakeGreenhouse([raw('design',title='Product Design Intern - Summer 2027',description='Prototype AI experiences. Test with real users. Portfolio showing interaction design required.')])
        self.assertEqual(self.run_service(sources=['greenhouse']).all_jobs[0].relevance_category,'EXCLUDED')

    def test_it_engineering_with_generic_code_duties_requires_review(self):
        self.clients['greenhouse']=FakeGreenhouse([raw('it',title='IT Engineer Intern - Summer 2027',description='Ship code. Python and Java. No project specified in advance.')])
        self.assertEqual(self.run_service(sources=['greenhouse']).all_jobs[0].relevance_category,'NEEDS_REVIEW')

    def test_published_and_updated_dates_remain_separate(self):
        self.assertEqual(self.run_service().all_jobs[0].published_at,'UNKNOWN')
        self.assertEqual(self.run_service().all_jobs[0].updated_at,'2025-01-08T00:00:00Z')

    def test_official_job_and_application_urls_are_separate(self):
        job=self.run_service().all_jobs[1]
        self.assertNotEqual(job.job_url,job.application_url)
        self.assertTrue(job.application_url.endswith('/apply'))

    def test_preview_does_not_open_sqlite_or_create_run(self):
        with patch('internship_agent.unified_discovery.JobDatabase',side_effect=AssertionError('SQLite must not open')):
            result=self.run_service()
        self.assertIsNone(result.run_id);self.assertFalse(self.db.exists())

    def test_explicit_save_saves_sorted_preview_only(self):
        result=self.run_service(save=True)
        self.assertEqual(result.newly_saved,2)
        with JobDatabase(self.db) as db:self.assertEqual(db.count_jobs(),2)

    def test_save_all_bypasses_preview_limit_explicitly(self):
        result=self.run_service(save=True,save_all=True)
        self.assertEqual(len(result.preview),2);self.assertEqual(result.newly_saved,3)
        with JobDatabase(self.db) as db:self.assertEqual(db.count_jobs(),3)

    def test_candidate_cap_overrides_are_explicit(self):
        service=self.service()
        with self.assertRaisesRegex(ConfigurationError,'max-candidates'):
            service.run(CONFIG,self.config_dir,limit=41)
        self.assertEqual(service.run(CONFIG,self.config_dir,limit=41,max_candidates=50).candidate_cap,50)

    def test_save_all_requires_explicit_save(self):
        with self.assertRaises(ConfigurationError):self.run_service(save_all=True)

    def test_repeated_run_is_idempotent(self):
        first=self.run_service(save=True,save_all=True)
        second=self.run_service(save=True,save_all=True)
        self.assertEqual(first.newly_saved,3);self.assertEqual(second.newly_saved,0)
        self.assertEqual(second.existing_skipped,3)
        with JobDatabase(self.db) as db:self.assertEqual(db.count_jobs(),3)

    def test_historical_greenhouse_source_identity_is_preserved(self):
        with JobDatabase(self.db) as db:
            existing=db.add_job(Job(title='Original title',company='Original company',source='greenhouse',source_job_id='g-board:gh-1')).record
        result=self.run_service(save=True,save_all=True)
        self.assertEqual(result.newly_saved,2)
        with JobDatabase(self.db) as db:self.assertEqual(db.get_job(existing.id),existing)

    def test_cross_platform_same_url_is_reported_not_merged(self):
        for filename,collection,_,_ in self.specs:
            p=self.config_dir/filename;d=yaml.safe_load(p.read_text());d[collection][0]['company_name']='Example Robotics';p.write_text(yaml.safe_dump(d))
        common='An internship engineering substantial machine learning model training pipeline. '*3
        self.clients={'greenhouse':FakeGreenhouse([raw('same',description=common)]),'lever':FakeLever([[raw('same',description=common)]]),'ashby':FakeAshby([raw('same',description=common)])}
        result=self.run_service(save=True,save_all=True)
        self.assertEqual(result.newly_saved,3)
        self.assertEqual(len(result.suspected_duplicates),3)
        with JobDatabase(self.db) as db:self.assertEqual(db.count_jobs(),3)

    def test_title_only_cross_platform_coincidence_is_not_a_duplicate(self):
        result=self.run_service()
        self.assertEqual(result.suspected_duplicates,[])

    def test_lever_partial_page_recovery_preserves_complete_pages(self):
        self.clients['lever']=FakeLever([[raw(f'l-{i}') for i in range(100)],[raw('late')]],fail_offset=100)
        first=self.run_service(sources=['lever'],save=True,save_all=True)
        self.assertEqual(first.coverage[0].status,'INCOMPLETE')
        self.assertEqual(first.newly_saved,100)
        self.clients['lever'].fail_offset=None
        resumed=self.run_service(sources=['lever'],save=True,save_all=True,resume=first.run_id)
        self.assertEqual(self.clients['lever'].calls,[0,100])
        self.assertEqual(resumed.coverage[0].raw_jobs,101)
        self.assertEqual(resumed.coverage[0].pages_fetched_this_command,1)
        with JobDatabase(self.db) as db:
            self.assertEqual(db.count_jobs(),101)
            self.assertEqual(db.get_run(first.run_id).status,'COMPLETED')

    def test_stale_running_run_is_explicitly_recovered(self):
        self.clients['ashby']=FakeAshby([raw('a-1')])
        original=self.clients['ashby'].fetch_board
        def crash(token):raise KeyboardInterrupt('simulated interruption')
        self.clients['ashby'].fetch_board=crash
        with self.assertRaises(KeyboardInterrupt):self.run_service(save=True,save_all=True)
        with JobDatabase(self.db) as db:run_id=db.list_runs()[0].run_id
        self.clients['ashby'].fetch_board=original
        resumed=self.run_service(save=True,save_all=True,resume=run_id)
        self.assertEqual(self.clients['greenhouse'].calls,['g-board'])
        self.assertEqual(self.clients['lever'].calls,[0])
        self.assertEqual(resumed.coverage[0].pages_fetched_this_command,0)

    def test_resume_rejects_changed_configuration_or_selection(self):
        self.clients['lever']=FakeLever([[raw(f'l-{i}') for i in range(100)]],fail_offset=0)
        first=self.run_service(save=True,save_all=True)
        with self.assertRaises(RunStateError):self.run_service(save=True,save_all=True,resume=first.run_id,sources=['lever'])

    def test_concurrent_save_lock_is_rejected_without_background_worker(self):
        with exclusive_run_lock(self.db):
            with self.assertRaises(RunStateError):
                with exclusive_run_lock(self.db):pass

    def test_28_jobs_and_historical_run_rows_are_preserved(self):
        with JobDatabase(self.db) as db:
            for i in range(28):db.add_job(Job(title=f'Historical {i}',company='Example'))
            old=db.list_jobs();prior=db.start_run('simulation','fingerprint');db.complete_run(prior.run_id);prior=db.get_run(prior.run_id)
        self.run_service(save=True,save_all=True)
        with JobDatabase(self.db) as db:
            self.assertEqual(db.list_jobs()[:28],old)
            self.assertEqual(db.get_run(prior.run_id),prior)

    def test_report_contains_coverage_exact_urls_eligibility_and_review(self):
        result=self.run_service()
        report=self.root/'report.md';write_unified_report(result,report)
        text=report.read_text()
        for term in ('Source coverage','Official job URL','Work authorization','NEEDS_REVIEW','Suspected cross-platform duplicates','Summer 2027'):
            self.assertIn(term,text)
        self.assertTrue(report.with_suffix('.json').is_file())

    def test_report_explicitly_marks_incomplete_board(self):
        self.clients['ashby']=FakeAshby(ValueError('bad data'))
        result=self.run_service();report=self.root/'report.md';write_unified_report(result,report)
        self.assertIn('INCOMPLETE',report.read_text());self.assertIn('bad data',report.read_text())




class LeverAdapterIntegrityTests(unittest.TestCase):
    def opener(self,responses):
        from io import BytesIO
        def call(request,timeout):
            data=responses.pop(0)
            response=BytesIO(json.dumps(data).encode());response.status=200;return response
        return call

    def test_real_adapter_rejects_repeated_pages(self):
        page=[{'id':str(i),'text':'Full time'} for i in range(2)]
        client=LeverClient(page_limit=2,min_interval=0,sleeper=lambda _:None,opener=self.opener([page,page]))
        with self.assertRaises(LeverDataError):list(client.iter_site_pages('example'))

    def test_real_adapter_final_page_and_start_offset(self):
        client=LeverClient(page_limit=2,min_interval=0,sleeper=lambda _:None,opener=self.opener([[{'id':'3','text':'Intern'}]]))
        pages=list(client.iter_site_pages('example',start_skip=2))
        self.assertEqual(pages[0][0],'example:2');self.assertEqual(len(pages),1)

    def test_malformed_list_entry_is_not_silently_counted_complete(self):
        client=LeverClient(min_interval=0,sleeper=lambda _:None,opener=self.opener([[None]]))
        with self.assertRaises(LeverDataError):list(client.iter_site_pages('example'))


class MigrationCheckpointTests(unittest.TestCase):
    def test_version_4_migration_has_backup_and_durable_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.sqlite3'
            with JobDatabase(path) as db:old=db.add_job(Job(title='Existing Intern',company='Example')).record
            connection=sqlite3.connect(path)
            try:
                connection.execute('DROP TABLE discovery_checkpoints');connection.execute('PRAGMA user_version=4');connection.commit()
            finally:connection.close()
            with JobDatabase(path) as db:
                self.assertTrue(db.migration_backup_path.is_file())
                self.assertEqual(db.get_job(old.id),old)
                run=db.start_run('unified_discovery','fp')
                db.save_discovery_checkpoint(run.run_id,'page:test:0',{'raw_count':1,'jobs':[]})
            with JobDatabase(path) as db:self.assertEqual(db.load_discovery_checkpoints(run.run_id)['page:test:0']['raw_count'],1)
