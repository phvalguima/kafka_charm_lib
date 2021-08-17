"""

Implements the BaseCoordinator from Charmhelpers on Operator Framework.

The OpsCoordinator subclasses Serial Coordinator. It masks the use of hookenv
primitives to deal with Juju and exposes Events and methods to the other
elements. This is possible because the BaseCoordinator does not use any of the
default files or unit databases to store its own state. Instead, it saves on
local file named: .charmhelpers.coordinator.OpsCoordinator. Therefore, no
conflicts are expected with the Operator Framework.

Also implements the RestartEvent. This event should be emitted
every time a restart is needed and will trigger the lock negotiation protocol
across the peer relation.

RestartEvent receives two arguments:
ctx: a dictionary containing current context when the RestartEvent was issued.
     this variable is not used in the restart logic itself, it is intended to
     let the user optionally update its own context once the restart has been
     done.

services: a list of strings. It is the list of services to be restarted.

It is important to understand that RestartEvent only restarts systemd services
using the service_restart from Charmhelpers.


How to implement it:


    class CharmBaseSubclass(...):

        on = RestartCharmEvent()

        state = StoredState()

        def on_restart_event(self, event):

            # OPTIONALLY: depending on how often RestartEvents are emitted,
            #  there is a good chance several of the RestartEvents will be
            #  stacked on top of each other.
            #  One example, that can happen because this unit was waiting
            #  for the lock to be released (if event.restart()) while
            #  processing all the hooks. In this case,
            #  several RestartEvents got stacked for the same lock.
            #  This check will allow to run the first restart event and
            #  discard subsequent events.
            #  The check can be extended to a dictionary if event.services
            #  change and get restarted independently.

            if not self.state.need_restart:
                # Discard all subsequent restart events.
                return

            # This is the logic that processes the restart
            if event.restart():
                # Restart was successful, if the charm is keeping track
                # of a context, that is the place it should be updated
                self.state.config_state = event.ctx

                # OPTIONALLY, set need_restart:
                self.state.need_restart = False
            else:
                # defer the RestartEvent as it is still waiting for the
                # lock to be released.
                event.defer()

        ...

        def __init__(self, *args):

            ...

            self.framework.observe(self.on.restart_event,
                                   self.on_restart_event)

            # Coordinator has logic that the leader unit should always run
            # at start of hookenv and at its end. Therefore it should be
            # called in __init__ and __del__, respectively.
            self.coordinator = OpsCoordinator()
            self.coordinator.resume()
            # OPTIONALLY, set a need_restart flag. Check on_restart_event
            # comments to better understand its use.
            self.state.set_default(need_restart=False)

        def __del__(self):
            # Run the atexit hookenv logic
            self.coordinator.release()

        ...

        def on_config_changed(self, event):
            ...
            # Collect the config changes to build a context
            # store it in config_state
            ...

            # Check if restart is needed. A context can be provided to be
            # used in RestartEvent's processing.
            # The self.services is a list of service names that will be
            # restarted.
            if _some_check_to_not_issue_too_many_restarts():
                self.on.restart_event.emit(self.ctx, services=self.services)
                # OPTIONALLY, set a flag that will signal if the process has
                # already restarted or not, check the on_restart_event above.
                self.state.need_restart = True

"""

import copy
import json
import logging

from ops.framework import (
    EventBase,
    EventSource
)
from ops.charm import CharmEvents

from charmhelpers.coordinator import Serial
from charmhelpers.core.host import (
    service_resume,
    service_restart,
    service_reload
)

logger = logging.getLogger(__name__)


class RestartEvent(EventBase):
    """
    RestartEvent holds the information necessary to restart all the services
    if the lock has been granted.

    The RestartEvent receives a list of services that should be restarted if
    the lock has been granted. It also receives a dict which is the context
    in which this Event has been called.

    If the RestartEvent receives the lock and is able to successfully restart
    the services, then the Charm should store the context as the most up-to-
    date version of what is running.

    Args:
        ctx: dictionary containing the status of the charm when the restart
             request has been issued
        services: list of services
    """

    def __init__(self, handle, ctx, services=[]):
        super().__init__(handle)
        self._ctx = json.dumps(ctx)
        self._svc = copy.deepcopy(services)

    def snapshot(self):
        super().snapshot()
        return {
            "ctx": self._ctx,
            "svc": ",".join(self._svc)
        }

    def restore(self, snapshot):
        super().restore(snapshot)
        self._ctx = snapshot["ctx"]
        self._svc = snapshot["svc"].split(",")

    @property
    def ctx(self):
        return self._ctx

    @property
    def svc(self):
        return self._svc

    def restart(self):
        """
        The restart method manages the OpsCoordinator and requests for the
        locks. Once the lock is granted, run the restart on each of the
        services that have been passed.
        """
        coordinator = OpsCoordinator()
        coordinator.resume()
        if coordinator.acquire('restart'):
            for ev in self.svc:
                # Unmask and enable service
                service_resume(ev)
                # Reload and restart
                service_reload(ev)
                service_restart(ev)
            # Now that restart is done, save lock state and release it.
            coordinator.release()
            # Inform that restart has been successful
            return True
        else:
            coordinator.release()
            # Still waiting for the lock to be granted.
            # Return False so this event can be deferred
            return False


class RestartCharmEvent(CharmEvents):
    """Restart charm events."""

    restart_event = EventSource(RestartEvent)


class OpsCoordinator(Serial):
    """
    Implements the OpsCoordinator logic and subclasses Serial.

    OpsCoordinator listens wraps around the charmhelpers Serial Coordinator
    logic and provides a simple interface to manage locks. It implements the
    logic that should used on atstart and atexit of hookenv.
    """

    def __init__(self):
        """Calls the super().__init__()"""
        logger.debug("coordinator.OpsCoordinator created")
        super().__init__()

    def handle_locks(self, unit):
        """
        Check if the unit is the leader. If so, it must run the handle()
        at least once in the hooks so the locks can be correctly managed.
        """
        logger.debug("coordinator.OpsCoordinator.handle_locks called")
        if not unit.is_leader():
            # Only the leader handles the locks
            return
        self.resume()
        self.release()

    def resume(self):
        """
        Run the startup methods needed for BaseCoordinator.

        handle() method must be called before any of the hooks and should
        be called at the begining of the method.
        handle() grants the locks to the units if ran by the leader.
        """
        logger.debug("coordinator.OpsCoordinator.resume called")
        self.initialize()
        self.handle()

    def release(self):
        """
        Capture the state and save it following a release event.

        According to the charm-helpers, those are the two methods called at
        hookenv.atexit().
        Therefore, release() should be called at the end of the method.
        It will release the lock if granted and flush the state to the file.
        """
        logger.debug("coordinator.OpsCoordinator.release called")
        self._release_granted()
        self._save_state()
