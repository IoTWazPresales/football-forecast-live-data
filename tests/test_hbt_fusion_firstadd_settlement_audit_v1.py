import datetime as dt
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hbt_fusion_firstadd_settlement_audit_v1 import audit, git_blob_sha


def fixture():
    c={'schemaVersion':'HBT-FUSION-FIRST-ADD-1','fixtureIdentityKey':'2026-10-30|fr.1|le havre ac|paris saint-germain|P1',
       'targetDate':'2026-10-30','capturedAt':'2026-10-30T16:41:39Z','sourceGeneratedAt':'2026-10-30T16:41:38Z','sourceSha256':'a'*64,
       'policy':{'cleanCalibrationEligible':False},'forecast':{'fixture':{'date':'2026-10-30','time':'18:00','league':'fr.1','home':'Le Havre AC','away':'Paris Saint-Germain'},
       'status':'RESEARCH_ONLY','predictionMode':'PRE-XI FUSION','executionEligible':False,'diagnostics':{'preKickoff':True},
       'probs':[.2,.25,.55],'layerPredictions':{'Fusion':[.2,.25,.55],'L4':[.3,.2,.5]},
       'scoreMarkets':{'hda':[.3,.2,.5],'oneX':.5,'x2':.7,'twelve':.8,'bttsYes':.6,'over25':.65}}}
    m={'schemaVersion':'HBT-INDEPENDENT-SETTLEMENT-1','fixtureIdentityKey':c['fixtureIdentityKey'],
       'category':'senior_men','resultStatus':'FT_90_VERIFIED','identityVerified':True,'kickoffVerified':True,
       'kickoffUtc':'2026-10-30T18:00:00Z','captureCommitTimeUtc':'2026-10-30T16:41:40Z',
       'captureGitCommit':'f'*40,'sourceSha256':'a'*64,'homeGoals90':1,'awayGoals90':5,
       'resultSources':['https://www.reuters.com/test','https://www.skysports.com/test']}
    return c,m

def run(c,m):
    b=(json.dumps(c)+'\n').encode();m['captureGitBlobSha']=git_blob_sha(b)
    return audit(b,m)

class FirstAddSettlement(unittest.TestCase):
    def test_positive_and_distinct_market_lineage(self):
        c,m=fixture();o=run(c,m)
        self.assertTrue(o['fusion1X2']['correctTopPick'])
        self.assertAlmostEqual(o['fusion1X2']['brier'],.2**2+.25**2+(.55-1)**2)
        self.assertAlmostEqual(o['fusionDerivedDC']['X2']['probability'],.8)
        self.assertAlmostEqual(o['L4ScoreDistributionMarkets']['x2']['probability'],.7)
        self.assertEqual(o['L4ScoreDistributionMarkets']['bttsYes']['actual'],1)
        self.assertIsNone(o['r5HypotheticalROI'])
    def test_rejects_post_kickoff_capture(self):
        c,m=fixture();c['capturedAt']='2026-10-30T18:01:00Z'
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_post_kickoff_commit(self):
        c,m=fixture();m['captureCommitTimeUtc']='2026-10-30T18:02:00Z'
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_womens_category(self):
        c,m=fixture();m['category']='women'
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_unverified_result(self):
        c,m=fixture();m['resultStatus']='EXTRA_TIME'
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_wrong_kickoff(self):
        c,m=fixture();m['kickoffUtc']='2026-10-30T19:00:00Z'
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_one_source(self):
        c,m=fixture();m['resultSources']=['https://www.reuters.com/test']
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_modified_capture_blob(self):
        c,m=fixture();b=(json.dumps(c)+'\n').encode();m['captureGitBlobSha']='f'*40
        with self.assertRaises(ValueError):audit(b,m)
    def test_rejects_wrong_source_hash(self):
        c,m=fixture();m['sourceSha256']='b'*64
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_mixed_l4_and_fusion_markets(self):
        c,m=fixture();c['forecast']['scoreMarkets']['x2']=.8
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_invalid_probability(self):
        c,m=fixture();c['forecast']['probs']=[.2,.3,.6]
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_non_p1(self):
        c,m=fixture();c['fixtureIdentityKey']=c['fixtureIdentityKey'].replace('|P1','|P2');m['fixtureIdentityKey']=c['fixtureIdentityKey']
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_non_integer_score(self):
        c,m=fixture();m['homeGoals90']=1.0
        with self.assertRaises(ValueError):run(c,m)
    def test_rejects_false_identity_proof(self):
        c,m=fixture();m['identityVerified']=False
        with self.assertRaises(ValueError):run(c,m)

if __name__=='__main__':unittest.main()
