# Readiness-loop experiment

`--mode selectors` uses DefaultSelector to manage the listener and idle client sockets. Only readable clients enter the bounded pool. A worker processes one exchange, then returns its reader and request count to the loop through a thread-safe queue. Buffered pipelined requests are resubmitted without waiting for another socket event. An explicit 256-connection cap bounds parked sockets.

This is a hybrid readiness loop, not an all-nonblocking async implementation: active header/body reads, upstream work, application handlers, and writes remain blocking in workers. It directly investigates idle persistent connections consuming worker slots. Slow active uploads can still exhaust workers. The default remains the simpler connection-owned thread pool.

Run matching protocol regressions with `HTTP_TEST_MODE=selectors python3 -m unittest discover -s tests -v`; the normal command tests the default. Tests that explicitly select a mode keep that mode. Run `python3 benchmarks/event_loop.py` for identical cached 1 KiB payloads, 1/4/8 persistent clients, twenty warm-up attempts, and three repetitions. Results include errors, percentiles, CPU, and sampled RSS.

Readiness registration belongs to the loop thread; workers communicate returned state through a queue. This prevents simultaneous readers on a connection. The selector polling interval introduces wake-up overhead that can hurt tiny-request throughput. Moving all active I/O into nonblocking state machines would be a separate, much larger experiment.

The first polling implementation recorded roughly 87/360/709 requests/s at 1/4/8 clients versus roughly 4,086/4,269/3,979 in the default mode. `results/selectors-polling.json` preserves that negative result. A socket-pair wakeup now immediately notifies the loop when a worker returns a connection, removing the fixed completion polling delay. `results/selectors.json` records the corrected comparison. This is an example of measuring and addressing an observed scheduling bottleneck.

After the wakeup correction, mean throughput was approximately 3,711/3,096/2,384 requests/s in selector mode versus 3,932/4,156/3,594 in the default mode. All recorded replies validated successfully. The hybrid still costs queueing/registrations on tiny active exchanges, so default thread ownership is retained. Its demonstrated benefit is parking many idle clients without holding a worker, not a throughput win for this workload.
