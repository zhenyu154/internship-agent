# Public copy: synthetic identities and timestamps; no live source verification.
"""Offline tests for evidence-based company research and registry expansion."""

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

import yaml

from internship_agent.ashby import load_ashby_registry, save_ashby_registry
from internship_agent.company_discovery import (
    CompanyCandidate, CompanyVerification, CompanyVerifier, SUPPORTED, UNSUPPORTED, REVIEW,
    register_companies, recognize_ats_url, write_research_report,
)
from internship_agent.config import ConfigurationError
from internship_agent.database import JobDatabase
from internship_agent.greenhouse import load_board_registry, save_board_registry
from internship_agent.lever import load_lever_registry, save_lever_registry
from internship_agent.models import Job
from internship_agent.public_http import PublicAccessError, PublicGetTransport, validate_https_url

ROOT=Path(__file__).resolve().parents[1]


def candidate(**kwargs):
    values=dict(company_name="Example Robotics", official_website="https://example.test/",
                official_careers_url="https://example.test/careers", evidence_url="https://example.test/careers",
                technical_focus="Robot learning", region="California", inclusion_reason="Robotics engineering",
                board_url="https://jobs.ashbyhq.com/example-robotics")
    return CompanyCandidate(**{**values,**kwargs})


def verified(**kwargs):
    values=dict(candidate=candidate(), ats_platform="Ashby", token="example-robotics",
                public_board_url="https://jobs.ashbyhq.com/example-robotics",
                verified_at="2025-01-10T00:00:00Z",status=SUPPORTED, reason="Ownership linked",
                raw_postings=4, ownership_confirmed=True,careers_verified=True)
    return CompanyVerification(**{**values,**kwargs})


class EvidenceTests(unittest.TestCase):
    def verifier(self, html, payload=None):
        class Transport:
            def page(self,url): return html
            def __call__(self,request,timeout=None):
                response=BytesIO(json.dumps(payload if payload is not None else {"jobs":[]}).encode())
                response.status=200
                return response
        return CompanyVerifier([candidate()],transport=Transport())

    def test_correct_supported_ats_url_recognition(self):
        cases=[("https://job-boards.greenhouse.io/example/jobs/123","Greenhouse","example"),
               ("https://boards.greenhouse.io/embed/job_board?for=example","Greenhouse","example"),
               ("https://jobs.lever.co/example/123","Lever","example"),
               ("https://jobs.ashbyhq.com/example/123?utm_source=x","Ashby","example")]
        for url,platform,token in cases:
            with self.subTest(url=url):
                self.assertEqual(recognize_ats_url(url)[:2],(platform,token))

    def test_company_identity_and_link_are_required_before_api(self):
        html='<h1>Example Robotics Careers</h1><a href="https://jobs.ashbyhq.com/example-robotics">Jobs</a>'
        result=self.verifier(html).verify(candidate())
        self.assertEqual(result.status,SUPPORTED)
        self.assertTrue(result.ownership_confirmed)

    def test_wrong_company_on_official_page_is_not_verified(self):
        html='<h1>Other Company</h1><a href="https://jobs.ashbyhq.com/example-robotics">Jobs</a>'
        result=self.verifier(html).verify(candidate())
        self.assertEqual(result.status,REVIEW)
        self.assertIn('company name',result.reason)

    def test_api_200_without_official_ownership_link_is_not_verified(self):
        result=self.verifier('<h1>Example Robotics Careers</h1>').verify(candidate())
        self.assertEqual(result.status,REVIEW)
        self.assertFalse(result.ownership_confirmed)

    def test_guessed_token_not_present_in_official_urls_is_rejected(self):
        html='<h1>Example Robotics</h1><a href="https://jobs.ashbyhq.com/actual">Jobs</a>'
        self.assertEqual(self.verifier(html).verify(candidate()).status,REVIEW)

    def test_documented_alias_allows_company_name_match(self):
        html='<h1>ER Robotics Careers</h1><a href="https://jobs.ashbyhq.com/example-robotics">Jobs</a>'
        self.assertEqual(self.verifier(html).verify(candidate(aliases=("ER Robotics",))).status,SUPPORTED)

    def test_missing_careers_url_is_review(self):
        self.assertEqual(self.verifier('Example Robotics').verify(candidate(official_careers_url='')).status,REVIEW)

    def test_untrusted_ownership_evidence_domain_is_rejected(self):
        result=self.verifier('Example Robotics').verify(candidate(evidence_url='https://unrelated.test/careers'))
        self.assertEqual(result.status,REVIEW)
        self.assertIn('official company domain',result.reason)

    def test_workday_employer_preserved_as_unsupported(self):
        html='<h1>Example Robotics Careers</h1><a href="https://example.wd5.myworkdayjobs.com/Careers">Jobs</a>'
        result=self.verifier(html).verify(candidate(board_url=''))
        self.assertEqual(result.status,UNSUPPORTED)
        self.assertEqual(result.ats_platform,'Workday')

    def test_malformed_public_api_response_does_not_verify_board(self):
        html='<h1>Example Robotics</h1><a href="https://jobs.ashbyhq.com/example-robotics">Jobs</a>'
        result=self.verifier(html,payload={"not_jobs":[]}).verify(candidate())
        self.assertEqual(result.status,REVIEW)

    def test_application_url_never_accepted_as_board(self):
        with self.assertRaises(PublicAccessError):
            recognize_ats_url('https://jobs.lever.co/example/123/apply')


class PublicNetworkTests(unittest.TestCase):
    def public_dns(self,*args,**kwargs):
        return [(2,1,6,'',('93.184.216.34',443))]

    def test_http_private_ip_localhost_and_untrusted_host_are_blocked(self):
        for url in ('http://example.test','https://localhost/a','https://127.0.0.1/a',
                    'https://10.0.0.1/a','https://example.test:8443/a','https://user:pass@example.test/a',
                    'https://other.test/a'):
            with self.subTest(url=url),self.assertRaises(PublicAccessError):
                validate_https_url(url,{'example.test','localhost','127.0.0.1','10.0.0.1'})

    def test_private_dns_resolution_is_blocked_before_open(self):
        opened=[]
        transport=PublicGetTransport({'example.test'},resolver=lambda *a,**k:[(2,1,6,'',('192.168.1.10',443))],opener=lambda *a,**k:opened.append(True))
        with self.assertRaises(PublicAccessError):
            transport(Request('https://example.test/',method='GET'))
        self.assertEqual(opened,[])

    def test_non_get_auth_and_application_endpoints_blocked(self):
        transport=PublicGetTransport({'example.test'},resolver=self.public_dns)
        for request in (Request('https://example.test/',method='POST'),
                        Request('https://example.test/',headers={'Authorization':'secret'}),
                        Request('https://example.test/apply',method='GET')):
            with self.assertRaises(PublicAccessError):
                transport(request)

    def test_unexpected_redirect_is_rejected(self):
        class Response(BytesIO):
            status=200
            def geturl(self): return 'https://other.test/'
        transport=PublicGetTransport({'example.test'},resolver=self.public_dns,opener=lambda *a,**k:Response(b'body'))
        with self.assertRaises(PublicAccessError):
            transport(Request('https://example.test/',method='GET'))

    def test_cached_request_does_not_repeat_network_call(self):
        calls=[]
        def opener(*args,**kwargs):
            calls.append(True)
            response=BytesIO(b'public');response.status=200;return response
        transport=PublicGetTransport({'example.test'},resolver=self.public_dns,opener=opener,interval=0)
        request=Request('https://example.test/',method='GET')
        for _ in range(2):
            with transport(request) as response:self.assertEqual(response.read(),b'public')
        self.assertEqual(len(calls),1)

    def test_request_budget_is_bounded(self):
        def opener(*args,**kwargs):
            response=BytesIO(b'public');response.status=200;return response
        transport=PublicGetTransport({'example.test'},resolver=self.public_dns,opener=opener,interval=0,max_requests=1)
        transport(Request('https://example.test/a',method='GET')).close()
        with self.assertRaises(PublicAccessError):transport(Request('https://example.test/b',method='GET'))

    def test_robots_disallow_is_respected(self):
        def opener(request,timeout=None):
            response=BytesIO(b'User-agent: *\nDisallow: /careers\n');response.status=200;return response
        transport=PublicGetTransport({'example.test'},resolver=self.public_dns,opener=opener,interval=0)
        with self.assertRaisesRegex(PublicAccessError,'robots'):
            transport.page('https://example.test/careers')


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.directory=Path(self.tmp.name)
        for name in ('greenhouse_boards.yaml','lever_sites.yaml','ashby_boards.yaml'):
            shutil.copyfile(ROOT/'tests'/'fixtures'/name,self.directory/name)
        self.before={p.name:p.read_bytes() for p in self.directory.glob('*.yaml')}

    def test_dry_run_never_writes_existing_registries(self):
        result=register_companies([verified()],self.directory)
        self.assertEqual(len(result['additions']),1)
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.directory.glob('*.yaml')})

    def test_explicit_save_and_repeated_save_are_idempotent(self):
        result=register_companies([verified()],self.directory,save=True)
        saved=(self.directory/'ashby_boards.yaml').read_bytes()
        second=register_companies([verified()],self.directory,save=True)
        self.assertEqual(len(result['additions']),1)
        self.assertEqual(second['additions'],[])
        self.assertEqual(second['duplicates_skipped'],1)
        self.assertEqual(saved,(self.directory/'ashby_boards.yaml').read_bytes())

    def test_original_entries_remain_identical_and_loadable(self):
        register_companies([verified()],self.directory,save=True)
        original=yaml.safe_load(self.before['ashby_boards.yaml'])['boards']
        current=yaml.safe_load((self.directory/'ashby_boards.yaml').read_text())['boards']
        self.assertEqual(current[:3],original)
        records=load_ashby_registry(self.directory/'ashby_boards.yaml')
        self.assertEqual(records[-1].evidence_url,'https://example.test/careers')
        save_ashby_registry(self.directory/'ashby_boards.yaml',records)
        self.assertEqual(load_ashby_registry(self.directory/'ashby_boards.yaml')[-1],records[-1])

    def test_duplicate_registry_identity_is_rejected(self):
        path=self.directory/'ashby_boards.yaml';data=yaml.safe_load(path.read_text())
        data['boards'].append(data['boards'][0].copy());path.write_text(yaml.safe_dump(data))
        with self.assertRaises(ConfigurationError):register_companies([],self.directory,save=True)

    def test_conflicting_board_ownership_leaves_files_unchanged(self):
        conflict=verified(candidate=candidate(company_name='Different Company'),token='example-ashby-alpha')
        with self.assertRaises(ConfigurationError):register_companies([conflict],self.directory,save=True)
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.directory.glob('*.yaml')})

    def test_existing_company_alias_skips_duplicate(self):
        alias=verified(candidate=candidate(company_name='Example Ashby Alias',aliases=('Example Ashby Alpha',)),token='example-ashby-alpha')
        result=register_companies([alias],self.directory,save=True)
        self.assertEqual(result['additions'],[])
        self.assertEqual(result['duplicates_skipped'],1)

    def test_unowned_api_success_cannot_be_registered(self):
        with self.assertRaises(ConfigurationError):
            register_companies([verified(ownership_confirmed=False)],self.directory,save=True)

    def test_unsupported_company_remains_in_research_report(self):
        result=verified(status=UNSUPPORTED,ats_platform='Workday',token='',ownership_confirmed=False)
        registration=register_companies([result],self.directory,save=True)
        report=self.directory/'report.md';write_research_report(report,[result],registration)
        self.assertIn('Example Robotics',report.read_text())
        self.assertIn('VERIFIED_UNSUPPORTED',report.read_text())
        self.assertEqual(registration['additions'],[])

    def test_greenhouse_and_lever_provenance_round_trip(self):
        cases=[("Greenhouse","new-greenhouse","greenhouse_boards.yaml",load_board_registry,save_board_registry,"https://boards.greenhouse.io/new-greenhouse"),
               ("Lever","new-lever","lever_sites.yaml",load_lever_registry,save_lever_registry,"https://jobs.lever.co/new-lever")]
        for platform,token,filename,loader,saver,board in cases:
            with self.subTest(platform=platform):
                result=verified(candidate=candidate(company_name=f"Example {platform}"),ats_platform=platform,token=token,public_board_url=board)
                register_companies([result],self.directory,save=True)
                loaded=loader(self.directory/filename)
                self.assertEqual(loaded[-1].verification_status,SUPPORTED)
                saver(self.directory/filename,loaded)
                self.assertEqual(loader(self.directory/filename)[-1].evidence_url,'https://example.test/careers')

    def test_alias_cannot_reassign_existing_company_to_different_board(self):
        result=verified(candidate=candidate(company_name='Example Ashby Alias',aliases=('Example Ashby Alpha',)),token='unrelated')
        with self.assertRaises(ConfigurationError):register_companies([result],self.directory,save=True)
        self.assertEqual(self.before,{p.name:p.read_bytes() for p in self.directory.glob('*.yaml')})

    def test_registries_update_without_opening_or_modifying_28_jobs(self):
        dbpath=self.directory/'jobs.sqlite3'
        with JobDatabase(dbpath) as database:
            for i in range(28):database.add_job(Job(title=f'Intern {i}',company='Example'))
            before=database.list_jobs()
        bytes_before=dbpath.read_bytes()
        with patch('internship_agent.database.JobDatabase',side_effect=AssertionError('Must not open jobs')):
            register_companies([verified()],self.directory,save=True)
        self.assertEqual(bytes_before,dbpath.read_bytes())
        with JobDatabase(dbpath) as database:self.assertEqual(before,database.list_jobs())
