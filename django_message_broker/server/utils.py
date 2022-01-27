from inspect import isawaitable
import types
from tornado.ioloop import PeriodicCallback
from tornado.log import app_log
from typing import Awaitable, Callable, Dict, Optional, Iterator
import weakref


class IntegerSequence:
    """Generates iterators of integer sequences."""
    def new_iterator(self, start: int = 0) -> Iterator[int]:
        """Returns an iterator which generates the next integer in a sequence when called.

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
        self, callback: Callable[[], Optional[Awaitable]], *args, **kwargs
    ) -> None:
        super().__init__(
            callback,  # type: ignore
            *args,
            **kwargs,
        )
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


class MethodRegistry:
    """
Meta class plug-in adding a dictionary of callable methods indexed by command name.

The class exposes a decorator that registers the method in a dictionary
indexed by a named command (as byte string). The dictionary of callable methods is
created when the class is imported; however, methods can only be bound to an instance
of the class when the class is instantiated.

When an instance of the class is instantiated then a copy of the dictionary containing
bound callable methods can be created by calling the `get_bound_callables` method passing
the instance of the class as a parameter.

Example usage:

.. code-block:: python

    class MathsByName:
        # Create a registry of math functions
        class MathFunctions(MethodRegistry):
            pass

        def __init__(self):
            # Bind methods to instance
            self.maths = MathsByName.MathFunctions.get_bound_callables(self)

        @MathFunctions.register(command=b"plusOne")
        def f1(self, a):
            return a + 1

        @MathFunctions.register(command=b"sumTwo")
        def f2(self, a, b):
            return a + b

    myMaths = MathsByName()
    plus_one = myMaths.maths[b"plusOne"](1)  # result = 2
    sum_two = myMaths.maths[b"sumTwo"](1, 2)  # result = 3
"""

    # This creates a shared registry across all MethodRegistry subclasses within an enclosing class
    # If more than one registry is required in a class then callables needs to be defined in the scope
    # of the subclass.
    callables: Dict[bytes, Callable] = {}

    @classmethod
    def register(cls, command: bytes = None) -> Callable:
        """Decorator to register a named function in the dictionary of callables.

        Args:
            command (bytes, optional): Name of the command.

        Raises:
            Exception: If no command is given.
            Exception: If the command has already been defined.
        """
        if command is None:
            raise Exception("Command must be named in the decorator.")

        if command in cls.callables:
            raise Exception(f"Command '{command}' can only be bound to one function.")

        def decorator(func: Callable) -> Callable:
            # We don't wrap the function, only register it with the command
            # and return the original function.
            cls.callables[command] = func
            return func

        return decorator

    @classmethod
    def get_bound_callables(cls, self) -> Dict[bytes, Callable]:
        """Given an instance of the class, returns a dictionary of named methods.

        Returns:
            Dict[bytes, Callable]: Dictionary of callable methods.
        """
        return {
            command: types.MethodType(func, self)
            for command, func
            in cls.callables.items()
        }
