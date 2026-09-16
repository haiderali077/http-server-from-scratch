"""Readiness loop for idle sockets; bounded workers perform active exchanges.

This is deliberately a hybrid, not an all-nonblocking application runtime.
Only the loop changes registrations; workers return state through a queue.
"""
import queue
import selectors
import socket
import time

if __package__:
    from .http_response import error_response
    from .transport import send_response
else:
    from http_response import error_response
    from transport import send_response


def run_reactor(listener, pool, exchange, stop, timeouts, drain, capacity):
    completed = queue.SimpleQueue()
    connections, active = set(), set()
    waiting = {}
    listener.setblocking(False)
    wake_read, wake_write = socket.socketpair()
    wake_read.setblocking(False)
    wake_write.setblocking(False)

    with wake_read, wake_write, selectors.DefaultSelector() as selector:
        selector.register(listener, selectors.EVENT_READ)
        selector.register(wake_read, selectors.EVENT_READ)

        def close(connection):
            if connection in waiting:
                selector.unregister(connection)
                del waiting[connection]
            connections.discard(connection)
            connection.close()

        def reject(connection):
            try:
                connection.settimeout(.1)
                send_response(connection, error_response(503))
            except OSError:
                pass
            close(connection)

        def execute(connection, reader, number):
            result = None
            try:
                result = exchange(connection, reader, number)
            finally:
                completed.put((connection, result))
                try:
                    wake_write.send(b"x")
                except OSError:
                    # A full wakeup buffer is already readable; closed means shutdown.
                    pass

        def submit(connection, reader, number):
            if pool.submit(execute, connection, reader, number):
                active.add(connection)
            else:
                reject(connection)

        def completions():
            while True:
                try:
                    connection, state = completed.get_nowait()
                except queue.Empty:
                    return
                active.discard(connection)
                if not state or stop.is_set():
                    close(connection)
                else:
                    reader, number = state
                    if reader.buffer:
                        submit(connection, reader, number)
                    else:
                        waiting[connection] = (reader, number, time.monotonic() + timeouts.idle)
                        selector.register(connection, selectors.EVENT_READ)

        try:
            while not stop.is_set():
                completions()
                for key, _ in selector.select(.01):
                    if key.fileobj is wake_read:
                        try:
                            while wake_read.recv(4096):
                                pass
                        except BlockingIOError:
                            pass
                        completions()
                    elif key.fileobj is listener:
                        try:
                            connection, _ = listener.accept()
                        except BlockingIOError:
                            continue
                        connections.add(connection)
                        if len(connections) > capacity:
                            reject(connection)
                        else:
                            waiting[connection] = (None, 0, time.monotonic() + timeouts.header)
                            selector.register(connection, selectors.EVENT_READ)
                    else:
                        connection = key.fileobj
                        reader, number, _ = waiting.pop(connection)
                        selector.unregister(connection)
                        submit(connection, reader, number)
                for connection, (_, number, deadline) in list(waiting.items()):
                    if time.monotonic() >= deadline:
                        if number == 0:
                            try:
                                connection.settimeout(.1)
                                send_response(connection, error_response(408))
                            except OSError:
                                pass
                        close(connection)
        finally:
            for connection in list(waiting):
                close(connection)
            deadline = time.monotonic() + drain
            while active and time.monotonic() < deadline:
                completions()
                time.sleep(.01)
            for connection in list(connections):
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                close(connection)
