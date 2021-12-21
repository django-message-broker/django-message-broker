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
        self.pc = WeakPeriodicCallback(self._callback, callback_time=100)
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
        # When we create the strong periodic callback the reference count
        # on the class will increase because the periodic callback references
        # the class.
        self.periodic_callback.start()
        self.assertEqual(sys.getrefcount(self.periodic_callback), 3)
        # When we stop the callback the reference count should reduce again.
        self.periodic_callback.stop()
        self.assertEqual(sys.getrefcount(self.periodic_callback), 2)
    
    def test_weak_ref(self):
        self.weak_periodic_callback = WeakPeriodicCallbackCase()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)
        # A weak referenced periodic callback does not increase the reference
        # count on the class.
        self.weak_periodic_callback.start()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)
        # When the weak referenced periodic callback stops the reference count
        # does not change.
        self.weak_periodic_callback.stop()
        self.assertEqual(sys.getrefcount(self.weak_periodic_callback), 2)      

if __name__ == '__main__':
    unittest.main()