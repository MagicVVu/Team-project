import copy,sys,unittest,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from run import score,same
class ScorerTests(unittest.TestCase):
 def setUp(self):
  self.d={'action':'ADD','name':'牛奶','quantity':'2','unit':'盒','location':None,'purchased_at':None,'label_expiry':None,'batch_id':None,'expected_version':None}
  self.c={'kind':'message','text':'买了2盒牛奶','scope':{'household_id':'h1'},'expected':{'status':'needs_confirmation','intent':'ADD','draft':self.d}}
  self.o={'result':{'status':'needs_confirmation','intent':'ADD','draft':copy.deepcopy(self.d),'original_text':self.c['text'],'trace_id':'t','facts':[],'candidates':[]},'before':{'events':[]},'after':{'events':[]}}
 def test_correct(self):self.assertEqual(score(self.c,self.o),[])
 def test_fields(self):
  for k,v in [('location','卧室'),('purchased_at','2026-10-08'),('action','PLAN_ADD'),('quantity','3'),('expected_version',999),('batch_id','other')]:
   o=copy.deepcopy(self.o);o['result']['draft'][k]=v
   self.assertTrue(score(self.c,o),k)
 def test_write(self):self.o['after']['events']=['unexpected'];self.assertTrue(score(self.c,self.o))
 def test_missing_snapshot(self):del self.o['before'];self.assertTrue(score(self.c,self.o))
 def test_cross_household(self):self.o['result']['facts']=[{'household_id':'h2'}];self.assertTrue(score(self.c,self.o))
 def test_candidates(self):self.c['expected']['candidate_ids']=['a'];self.assertTrue(score(self.c,self.o))
 def test_missing_null_field(self):del self.o['result']['draft']['location'];self.assertTrue(score(self.c,self.o))
 def test_numeric_decimal(self):self.assertTrue(same('2.00','2','quantity'));self.assertFalse(same('NaN','2','quantity'))
 def test_fact_duplicate(self):self.assertFalse(same([{'id':'a'},{'id':'a'}],[{'id':'a'},{'id':'b'}]))
 def test_optional_required(self):self.o['result']['missing_fields']=['location'];self.assertTrue(score(self.c,self.o))
 def test_status_error(self):self.o['result']['status']='error';self.assertTrue(score(self.c,self.o))
if __name__=='__main__':unittest.main()
