import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from research.review_app import Store, Conflict


class ReviewStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'private').mkdir()
        (self.root/'manifest.json').write_text(json.dumps({'examples':[{'id':'E01','private_labels':'private/E01.json','source':{},'images':[]}]}))
        (self.root/'private/E01.json').write_text(json.dumps({'id':'E01'}))
        self.output = self.root/'annotations.json'
        self.store = Store(self.root,self.output)
        self.request = {'id':'E01','revision':0,'annotation':{'status':'issue','issues':['tracking'],'notes':'中文备注','expected':'小幅向左'}}

    def tearDown(self):
        self.temp.cleanup()

    def test_saved_annotation_survives_store_restart(self):
        result = self.store.update(self.request)
        self.assertEqual(result['revision'],1)
        self.assertEqual(Store(self.root,self.output).snapshot()['annotations']['E01']['notes'],'中文备注')

    def test_stale_tab_cannot_overwrite_saved_annotation(self):
        self.store.update(self.request)
        with self.assertRaises(Conflict):
            self.store.update(self.request)
        self.assertEqual(self.store.snapshot()['annotations']['E01']['revision'],1)

    def test_invalid_case_and_fields_do_not_create_file(self):
        for invalid in [{**self.request,'id':'other'},{**self.request,'annotation':{**self.request['annotation'],'status':'unexpected'}},{**self.request,'annotation':{**self.request['annotation'],'issues':['unknown']}}]:
            with self.assertRaises(ValueError):
                self.store.update(invalid)
        self.assertFalse(self.output.exists())

    def test_dataset_identity_is_checked(self):
        self.store.update(self.request)
        content = json.loads(self.output.read_text());content['dataset']='/other';self.output.write_text(json.dumps(content))
        with self.assertRaises(ValueError):
            Store(self.root,self.output)


if __name__=='__main__':
    unittest.main()
