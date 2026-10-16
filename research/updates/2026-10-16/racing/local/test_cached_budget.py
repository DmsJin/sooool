import json,pathlib,tempfile,unittest
from run import Budget
class CachedBudget(unittest.TestCase):
 def test_old_charges_preserved_and_pricing_follows_reservation(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'budget.json';p.write_text(json.dumps({'limit_usd':30,'charged_upper_usd':12,'reserved':{},'stages':{'old':12}}));b=Budget(p,cache_aware=True);rid=b.reserve('x',[],'new',6)
   cost=Budget(p).settle(rid,{'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':900}})
   self.assertAlmostEqual(cost,.008844);s=json.loads(p.read_text());self.assertEqual(s['stages']['old'],12);self.assertAlmostEqual(s['charged_upper_usd'],12.008844)
 def test_unknown_and_bad_cache_metadata_are_conservative(self):
  with tempfile.TemporaryDirectory() as d:
   b=Budget(pathlib.Path(d)/'b.json',cache_aware=True);rid=b.reserve('x',[],'new',6);self.assertGreater(b.settle(rid,None),.03)
   rid=b.reserve('x',[],'new',6);self.assertAlmostEqual(b.settle(rid,{'input_tokens':1000,'output_tokens':100,'input_tokens_details':{'cached_tokens':1001}}),.0231)
 def test_long_context_is_rejected_before_price_caps_become_invalid(self):
  with tempfile.TemporaryDirectory() as d:
   b=Budget(pathlib.Path(d)/'b.json',cache_aware=True)
   with self.assertRaisesRegex(RuntimeError,'short-context'):b.reserve('x',[],'new',6,additional_input_tokens=273000)
if __name__=='__main__':unittest.main()
