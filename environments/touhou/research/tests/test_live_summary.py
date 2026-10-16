import unittest
from research.live_summary import add_brief_schema, validate_brief, brief_prompt
from research.wire_schema import grounded_schema
from research.scheduler import parse_plan

class LiveSummaryTests(unittest.TestCase):
    def test_native_english_prompt(self):
        prompt=brief_prompt("No explanation.","en")
        self.assertIn("English public decision summary",prompt)
        self.assertNotIn("No explanation.",prompt)
        self.assertNotIn("Chinese",prompt)
        with self.assertRaises(ValueError):brief_prompt("test","unknown")

    def test_public_summary_never_rewrites_keys(self):
        answer={'brief':'向左避弹。','plan':[{'move':7,'shoot':1,'focus':1,'bomb':0,'duration':12}]}
        self.assertEqual(validate_brief(answer),'向左避弹。')
        self.assertEqual(parse_plan(answer)[0].keys,[7,1,1,0])
        self.assertEqual(parse_plan(answer)[0].duration,12)

    def test_missing_summary_is_invalid_even_with_legal_plan(self):
        for brief in (None,'','  ','x'*61):
            with self.assertRaises(ValueError):validate_brief({'brief':brief})

    def test_schema_extension_preserves_baseline(self):
        original=grounded_schema()
        extended=add_brief_schema(original)
        self.assertNotIn('brief',original['properties'])
        self.assertIn('brief',extended['required'])
        self.assertEqual(extended['properties']['plan'],original['properties']['plan'])
        with self.assertRaises(ValueError):add_brief_schema(None)

class EarlySummaryTests(unittest.TestCase):
    def test_brief_is_validated_before_early_publication(self):
        import tempfile
        from pathlib import Path
        from research.run_episode import DecisionPool
        with tempfile.TemporaryDirectory() as tmp:
            pool=DecisionPool({'decision_brief':True},Path(tmp))
            answer={'brief':'向左避弹。','plan':[[7,1,1,0,12]]}
            try:
                pool.publish_early(Path(tmp),{'answer':answer,'meta':{}})
                result=pool.take_early(Path(tmp))
                self.assertEqual(result['brief'],answer['brief'])
                self.assertEqual(result['plan'],answer['plan'])
                with self.assertRaises(ValueError):
                    pool.publish_early(Path(tmp),{'answer':{'plan':answer['plan']},'meta':{}})
                self.assertIsNone(pool.take_early(Path(tmp)))
            finally:pool.close()

if __name__=='__main__':unittest.main()
