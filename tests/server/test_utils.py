import sys
import unittest
from django_message_broker.server.utils import IntegerSequence, WeakPeriodicCallback, PeriodicCallback

class IntegerSequenceTests(unittest.TestCase):

    def test_next(self):
        integer_sequence = IntegerSequence().new_iterator()
        self.assertEqual(next(integer_sequence), 0)
        self.assertEqual(next(integer_sequence), 1)

    def test_next_with_none_zero_start(self):
        integer_sequence = IntegerSequence().new_iterator(start=10)
        self.assertEqual(next(integer_sequence), 10)
        self.assertEqual(next(integer_sequence), 11)


class PeriodicCallbackCase:
    def start(self):
        self.pc = PeriodicCallback(self._callback, callback_time=100)
        self.pc.start()

    def stop(self):
        self.pc.stop()
        del self.pc

    def _callback(self):
        pass


class WeakPeriodicCallbackCase:
    def start(self):
        self.pc = WeakPeriodicCallback(self._callback, callback_time=1000)
        self.pc.start()

    def stop(self):
        self.pc.stop()
        del self.pc

    def _callback(self):
        pass


class WeakPeriodCallbackTests(unittest.TestCase):

    def test_strong_ref(self):
        self.periodic_callback = PeriodicCallbackCase()
        self.assertEqual(sys.getrefcount(self.periodic_callback), 2)
        self.periodic_callback.start()
        self.assertEqual(sys.getrefcount(self.periodic_callback), 3)
        self.periodic_callback.stop()
        self.assertEqual(sys.getrefcount(self.periodic_callback), 2)
    
    def test_weak_ref(self):
        self.weak_periodic_callback = WeakPeriodicCallbackCase()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)
        self.weak_periodic_callback.start()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)
        self.weak_periodic_callback.stop()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)      

if __name__ == '__main__':
    unittest.main()