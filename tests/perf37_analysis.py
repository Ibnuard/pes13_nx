from pathlib import Path
import importlib.util
import tempfile
import unittest
p=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('analysis',p/'tools/analyze-perf37.py')
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

class Analysis(unittest.TestCase):
    def parse(self,text):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'test.log'; f.write_text(text); return a.parse(f)
    def test_word_counts_and_separate_intervals(self):
        r=self.parse('[PERF8] uptime_s=10 interval_ms=10000 presents=120\n'
            '[JIT37] 176w samples=10 word_dropped=1 block_dropped=0\n'
            '[JIT37-WORDS] 176w 1e22c108:4 1e622820:3 d5033bbf:2\n'
            '[JIT37-BLOCK] 176w guest=112fb90 guest_bytes=656 arm_bytes=7064 samples=8\n'
            '[PERF8] uptime_s=20 interval_ms=10000 presents=300\n'
            '[JIT37] 176w samples=1 word_dropped=0 block_dropped=0\n'
            '[JIT37-WORDS] 176w d503201f:1\n')
        self.assertEqual(r['jit_thread_intervals'],2)
        record=r['rows'][0]['jit']['176w']
        self.assertEqual(record['categories'],{'float_conversion':4,'float_other':3,'barrier_or_wait':2})
        self.assertEqual(record['blocks'][0]['guest'],0x112fb90)
        self.assertEqual(r['rows'][1]['jit']['176w']['samples'],1)
    def test_incomplete_or_duplicate_words(self):
        header='[PERF8] uptime_s=10 interval_ms=10000 presents=120\n[JIT37] 4w samples=2 word_dropped=0 block_dropped=0\n'
        for words in ('[JIT37-WORDS] 4w d503201f:1\n','[JIT37-WORDS] 4w d503201f:1 d503201f:1\n'):
            with self.assertRaises(ValueError): self.parse(header+words)
    def test_quiet_log_has_no_invented_samples(self):
        r=self.parse('[PERF8] uptime_s=10 interval_ms=10000 presents=120\n')
        self.assertEqual(r['jit_thread_intervals'],0)

if __name__=='__main__': unittest.main()
