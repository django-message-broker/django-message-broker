from inspect import isawaitable
from tornado.ioloop import PeriodicCallback
from tornado.log import app_log
from typing import Awaitable, Callable, Optional, Iterator, Sequence
import weakref


class IntegerSequence:
    def new_iterator(self, start: int = 0) -> Iterator[int]:
        """Returns an iterator which generates the next integer in a sequence when called

        Args:
            start (int, optional): Starting number of the sequence. Defaults to 0.

        Yields:
            Iterator[int]: Iterator generating the next integer in a sequence.
        """
        sequence = start
        while True:
            yield sequence
            sequence += 1


class WeakPeriodicCallback(PeriodicCallback):
    """Implementation of Tornado PeriodCallback establishing a weak reference to the callable function.

    A weak reference is required when the periodic callback is established in the initialization of a
    class to a callback method within the same class. In this situation the periodic callback holds a
    reference to an object within the class and the class can neither be deleted or garbage collected.
    This can lead to a memory leak. Establishing a weak link between the periodic callback and the
    callback method allows the callback to be removed from the event loop and the class deleted.
    """

    def __init__(
        self,
        callback: Callable[[], Optional[Awaitable]],
        *args,
        **kwargs,
    ) -> None:
        super().__init__(
            callback,  # type: ignore
            *args,
            **kwargs)
        # This overwrites the strong reference to the callback established in the base class.
        self.callback = weakref.WeakMethod(callback)

    async def _run(self) -> None:
        if not self._running:
            return
        try:
            # If the reference does not exist then remove the callback from the event loop.
            callback = self.callback()
            if callback is None:
                self.stop
            else:
                val = callback()
                if val is not None and isawaitable(val):
                    await val
        except Exception:
            app_log.error("Exception in callback %r", self.callback, exc_info=True)
        finally:
            self._schedule_next()
