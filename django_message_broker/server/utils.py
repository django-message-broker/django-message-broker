"""
Additional functionality used within the Django Message Broker:

*   IntegerSequence - Iterator returning the next integer when accessed.
*   WeakPeriodicCallback - Modifies Tornado Periodic Callback with weak method references.
*   MethodProxy - Creates a register of weak references to methods.
*   WaitFor - Asyncio method to wait upon multiple coroutines or events.
*   MethodRegistry - Implements a decorator in a class to auto-create a registor of methods.
"""

import asyncio
from inspect import isawaitable
import types
from tornado.ioloop import PeriodicCallback
from tornado.log import app_log
from typing import Any, Awaitable, Callable, Dict, List, Optional, Iterator
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
        """Method called after the time that future is scheduled to run."""
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


class MethodProxy:
    """Creates a registry to proxy strong function references with weak ones."""

    hive: Dict[int, Callable] = dict()

    @classmethod
    def register(cls, callback: Callable) -> Callable:
        """Registers a callback in a registry of callable methods and returns
        a callback with a weakref to the original callback method.

        Args:
            callback (Callable): Original callback method.

        Raises:
            ReferenceError: If the referenced callable has already been garbage
                            the terminates future and propagates into enclosing
                            waiting code.

        Returns:
            Callable: Weakref callable to the original callback method.
        """
        callback_ref = hash(callback)
        weak_callback = weakref.WeakMethod(callback)

        def proxy_callable(*args: List[Any], **kwargs: Dict[str, Any]) -> Any:
            """Proxy method weak referencing an actual method.

            Raises:
                ReferenceError: Actual method no longer exists.

            Returns:
                Any : Returns value from the original method.
            """
            callback = weak_callback()
            if callback is None:
                raise ReferenceError
            else:
                return_value = callback(*args, **kwargs)

            return return_value

        cls.hive[callback_ref] = proxy_callable

        return cls.hive[callback_ref]

    @classmethod
    def unregister(cls, callback: Callable) -> None:
        """Removes a callable method from the registry.

        Args:
            callback (Callable): Callable method to unregister
        """
        callback_ref = hash(callback)
        try:
            del cls.hive[callback_ref]
        except KeyError:
            pass


class WaitFor:
    """Waits for a combination of events to occur before continuing code execution.

    The code creates weak referenced callbacks which are triggered when an event in
    the list is set. The class exposes two asyncio methods:

    * ``one_event()`` - Which is triggered when any one of the events is set.
    * ``all_events()`` - Which is triggered when all the events are set.
    """

    def __init__(self, events: List[asyncio.Event]) -> None:
        """Takes a list of asyncio events as arguments.

        Args:
            events (List[Event]): List of events to monitor.
        """
        self.events = events
        self.tasks = [asyncio.create_task(event.wait()) for event in events]

        proxy_callback = MethodProxy.register(self._callback)
        for task in self.tasks:
            task.add_done_callback(proxy_callback)
        self.total_events = len(events)
        self.all = asyncio.Event()
        self.one = asyncio.Event()

    def _callback(self, task: asyncio.Task) -> None:
        """Callback when an event is set. The callback is proxied so that the
        method reference is weak, enabling this class to be garbage collected
        before the task is complete.

        Args:
            task (_type_): Asyncio callbacks are passed with the task as argument.
        """
        events_set = [event.is_set() for event in self.events]
        event_count = sum(events_set)
        if event_count > 0:
            self.one.set()
        if event_count == self.total_events:
            self.all.set()

    async def all_events(self) -> None:
        """Waits until all events are set."""
        await self.all.wait()
        MethodProxy.unregister(self._callback)

    async def one_event(self) -> None:
        """Waits until any one event is set."""
        await self.one.wait()
        MethodProxy.unregister(self._callback)

    def __del__(self) -> None:
        """Remove any outstanding tasks from the event loop."""
        for task in self.tasks:
            task.cancel()


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
        sum_two = myMaths.maths[b"sumTwo"](1, 2)  # result = 3"""

    # This creates a shared registry across all MethodRegistry subclasses within an enclosing class
    # If more than one registry is required in a class then callables needs to be defined in the scope
    # of the subclass.
    callables: Dict[bytes, Callable] = {}

    @classmethod
    def register(cls, command: Optional[bytes] = None) -> Callable:
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
            """Decorator registering function in the register.

            Args:
                func (Callable): Callable function to register.

            Returns:
                Callable: Passes the original function to the interpreter.
            """
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
            for command, func in cls.callables.items()
        }
