#! /bin/python3

"""
Manage ideal number of "agent" like resources in Resalloc.
"""

import subprocess
import time
import logging

from resalloc.client import (
    Connection as ResallocConnection,
    Ticket,
)

RESALLOC_SERVER = "http://localhost:49100"


class SpawnerPool:
    """
    Manage ideal number of "agent" like resources in Resalloc.
    """
    sleep = 30

    def __init__(self, resalloc_connection, logger):
        self.tags = ["arch_x86_64"]
        # TODO: use a persistent storage so we can restart the process
        self.tickets = []
        self.conn = resalloc_connection
        self.log = logger

    def call_converge_to(self):
        """ Execute the configured hook script """
        while True:
            result = subprocess.run(["./hook-converge-to"], stdout=subprocess.PIPE, check=False)
            if result.returncode == 0:
                try:
                    return int(result.stdout.decode("utf-8").strip())
                except ValueError:
                    pass

            self.log.debug("Failing to run converge-to hook")

    def call_take(self, data):
        """
        Call hook that prepares the resource
        """
        return not subprocess.run(["./hook-take", f"{data}"], check=True)

    def call_release(self, data):
        """
        Call hook that releases the resource
        """
        result = subprocess.run(["./hook-release", f"{data}"], check=False)
        return not result.returncode

    def start(self, count):
        """ Start N agent-like resources """
        self.log.info("Starting %s resources", count)
        for _ in range(count):
            ticket = self.conn.newTicket(self.tags)
            self.log.debug("Taking ticket id %s", ticket.id)
            self.tickets.append(ticket.id)
            data = ticket.wait()
            self.call_take(data)

    def try_to_stop(self, to_stop):
        """
        Attempt to stop TO_STOP resources by closing Resalloc tickets.  Not all
        the resources may be closed at this time.
        """
        self.log.info("Trying to stop %s resources", to_stop)
        stopped = 0
        for ticket_id in self.tickets:
            if stopped >= to_stop:
                break

            ticket = Ticket(ticket_id, connection=self.conn)
            data = ticket.collect()
            if not self.call_release(data):
                self.log.debug("Can't release %s", ticket.id)
                continue

            self.log.debug("Closing ticket %s", ticket.id)
            ticket.close()
            self.tickets.remove(ticket_id)
            stopped += 1


    def loop(self):
        """
        Periodically query the ideal number of builders, and attempt to converge
        to the ideal state.
        """
        while True:
            start = time.time()
            todo = self.call_converge_to() - len(self.tickets)
            if todo > 0:
                self.start(todo)
            elif todo < 0:
                self.try_to_stop(-todo)

            # TODO: we should check that tickets aren't in FAILED state

            took = time.time() - start
            sleep = self.sleep - took
            if sleep > 0:
                self.log.debug("Sleeping %ss", sleep)
                time.sleep(sleep)


def _main():
    logging.basicConfig(
        level=logging.DEBUG,
        format='[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    log = logging.getLogger()
    conn = ResallocConnection(RESALLOC_SERVER, request_survives_server_restart=True)
    spawner = SpawnerPool(conn, log)
    spawner.loop()


if __name__ == "__main__":
    _main()
