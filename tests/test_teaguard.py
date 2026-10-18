import copy
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import numpy as np

from server import make_handler
from teaguard.model import FIELDS, ROOT, day_phase, features, load_weather, split_name, target
from teaguard.service import TeaService, bounded_number


class TeaGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = load_weather()
        cls.service = TeaService(cls.rows)
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),make_handler(cls.service))
        cls.thread = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def test_01_public_data_full_coverage(self):
        self.assertEqual(len(self.rows),4018)
        self.assertEqual(self.rows[0]['date'],'2015-01-01')
        self.assertEqual(self.rows[-1]['date'],'2025-12-31')

    def test_02_features_do_not_read_future(self):
        index=3700
        altered=copy.deepcopy(self.rows)
        for r in altered[index+1:]:
            for f in FIELDS:r[f]+=10000
        np.testing.assert_array_equal(features(self.rows,index)[0],features(altered,index)[0])

    def test_03_inference_requires_only_past(self):
        index=3700
        full=self.service.model.predict_index(index)[0]
        past=self.service.model.predict_index(index,self.rows[:index+1])[0]
        np.testing.assert_array_equal(full,past)

    def test_04_training_labels_never_cross_boundary(self):
        for i,split in zip(self.service.model.indices,self.service.model.splits):
            if split=='train':self.assertLessEqual(self.rows[i+7]['date'],'2021-12-31')
            if split=='validation':self.assertLessEqual(self.rows[i+7]['date'],'2023-12-31')
            if split=='calibration':self.assertLessEqual(self.rows[i+7]['date'],'2024-12-31')

    def test_05_cross_year_windows_are_purged(self):
        self.assertEqual(split_name('2021-12-29','2022-01-05'),'purged')
        self.assertEqual(split_name('2024-12-30','2025-01-06'),'purged')

    def test_06_target_recomputed_independently(self):
        i=3700
        expected=[max(self.rows[k][FIELDS[0]] for k in range(i+1,i+4)),sum(self.rows[k][FIELDS[3]]-self.rows[k][FIELDS[2]] for k in range(i+1,i+8))]
        np.testing.assert_allclose(target(self.rows,i),expected)

    def test_07_scenario_does_not_mutate_public_rows(self):
        before=json.dumps(self.rows,sort_keys=True)
        self.service.analyze({'scenario':'hot_dry'})
        self.assertEqual(before,json.dumps(self.rows,sort_keys=True))

    def test_08_simulation_does_not_borrow_real_future_outcomes(self):
        response=self.service.analyze({'scenario':'hot_dry'})
        self.assertIsNone(response['verification'])
        self.assertEqual(response['evidence_kind'],'AI_AUTHORED_INPUT_SENSITIVITY_SCENARIO')

    def test_09_recent_balance_is_exact(self):
        r=self.service.analyze({})
        i=self.service.positions[r['date']]
        expected=sum(row[FIELDS[3]]-row[FIELDS[2]] for row in self.rows[i-6:i+1])
        self.assertAlmostEqual(r['recent']['balance_7d'],round(expected,1))

    def test_10_unadmitted_balance_model_never_drives_actions(self):
        r=self.service.analyze({'date':'2025-07-15'})
        self.assertFalse(r['outlook'][1]['used_for_actions'])
        self.assertLess(r['recent']['balance_7d'],15)
        self.assertNotIn('soil',[a['id'] for a in r['actions']])

    def test_11_wet_soil_simulation_changes_recommendation(self):
        r=self.service.analyze({'scenario':'hot_dry','soil':'moist'})
        action=next(a for a in r['actions'] if a['id']=='soil')
        self.assertIn('湿润',action['title'])
        self.assertIn('不生成补水操作',action['reason'])

    def test_12_date_outside_test_is_rejected(self):
        for day in ['2024-07-15','2025-12-31','garbage',None,[]]:
            with self.subTest(day=day),self.assertRaises(ValueError):self.service.analyze({'date':day})

    def test_13_nonfinite_and_boolean_thresholds_rejected(self):
        for value in ['NaN','Infinity',float('inf'),True,{},[35]]:
            with self.subTest(value=str(value)),self.assertRaises(ValueError):bounded_number(value,35,28,42)

    def test_14_out_of_range_thresholds_rejected(self):
        for value in [0,100,-20]:
            with self.assertRaises(ValueError):self.service.analyze({'heat_threshold':value})

    def test_15_unknown_scenarios_rejected(self):
        for value in ['other',None,[]]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.service.analyze({'scenario':value})

    def test_16_non_object_request_rejected(self):
        for args in [[],None,12,'text']:
            with self.assertRaises(ValueError):self.service.analyze(args)

    def test_17_identical_inputs_same_receipt(self):
        a=self.service.analyze({})
        b=self.service.analyze({})
        self.assertEqual(a,b)
        self.assertNotEqual(a['run_id'],self.service.analyze({'scenario':'hot_dry'})['run_id'])

    def test_18_finite_output_for_all_scenarios(self):
        for scenario in ['historical','hot_dry','wet']:
            r=self.service.analyze({'scenario':scenario})
            json.dumps(r,allow_nan=False)

    def test_19_health_and_html_http(self):
        for path in ['/','/app.js','/style.css','/api/health','/api/bootstrap','/api/evidence']:
            with self.subTest(path=path),urllib.request.urlopen(self.base+path) as response:
                self.assertEqual(response.status,200)
                self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')

    def test_20_http_invalid_body_returns400(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b'{bad',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,400)

    def test_21_http_wrong_origin_rejected(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,403)

    def test_22_http_nan_rejected(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b'{"heat_threshold":NaN}',headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,400)

    def test_23_http_body_limit(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b' '*17000,headers={'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,413)

    def test_24_arbitrary_file_route_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(self.base+'/../data/PROVENANCE.json')
        self.assertEqual(caught.exception.code,404)

    def test_25_live_request_returns_analysis(self):
        req=urllib.request.Request(self.base+'/api/analyze',data=b'{"scenario":"wet"}',headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(json.load(response)['scenario'],'wet')

    def test_26_heldout_failure_remains_visible(self):
        r=self.service.model.report
        self.assertEqual(r['test_metrics']['balance_7d']['selected']['recall'],0)
        self.assertEqual(r['product_admission']['balance_7d'],'EXPLORATORY_ONLY_NOT_USED_FOR_ACTIONS')


if __name__=='__main__':unittest.main(verbosity=2)
