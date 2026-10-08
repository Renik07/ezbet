"""Separate worker process: python -m app.worker (or services.api.app.worker locally)."""
import logging
import signal
import threading
from uuid import uuid4

from .jobs import JobQueue

WORKER_LOCK_KEY = 4815162348
logger = logging.getLogger(__name__)


class PipelineWorker:
    def __init__(self, repository, *, heartbeat_seconds=30):
        self.repository = repository
        self.queue = JobQueue(repository)
        self.worker_id = str(uuid4())
        self.heartbeat_seconds = heartbeat_seconds

    def run_once(self, run_pipeline):
        with self.repository.connect() as lock_connection:
            locked = lock_connection.execute('SELECT pg_try_advisory_lock(%s)', (WORKER_LOCK_KEY,)).fetchone()[0]
            lock_connection.commit()
            if not locked:
                return False
            try:
                self.queue.recover_stale()
                job = self.queue.claim(self.worker_id)
                if job is None:
                    return False
                finished = threading.Event()
                ownership_lost = threading.Event()

                def heartbeat():
                    while not finished.wait(self.heartbeat_seconds):
                        try:
                            # Verify the session holding the exclusive worker lock is still alive.
                            lock_connection.execute('SELECT 1')
                            lock_connection.commit()
                            if not self.queue.heartbeat(job['id'], self.worker_id):
                                ownership_lost.set()
                                return
                        except Exception:
                            logger.exception('Worker heartbeat failed')
                            ownership_lost.set()
                            return

                thread = threading.Thread(target=heartbeat, name='worker-heartbeat', daemon=True)
                thread.start()
                try:
                    response = run_pipeline(force=job['force'], should_continue=lambda: not ownership_lost.is_set())
                    result = response.model_dump(mode='json', by_alias=True)
                    failures = [getattr(response, stage).reason for stage in ('ingest', 'enrichment', 'editorial', 'publish')
                                if getattr(response, stage).reason.startswith('error:') or getattr(response, stage).reason == 'locked']
                    if ownership_lost.is_set():
                        raise RuntimeError('Worker lost ownership; execution stopped between stages.')
                    self.queue.finish(job['id'], self.worker_id, result=result,
                                      error='; '.join(failures) if failures else None)
                except Exception as error:
                    logger.exception('Worker job failed: %s', job['id'])
                    self.queue.finish(job['id'], self.worker_id, error=str(error))
                finally:
                    finished.set()
                    thread.join(timeout=15)
                return True
            finally:
                if not lock_connection.closed:
                    lock_connection.execute('SELECT pg_advisory_unlock(%s)', (WORKER_LOCK_KEY,))
                    lock_connection.commit()


def main():
    from . import runtime
    from .bootstrap import _initialize_runtime
    from .pipeline import _run_pipeline_scheduler
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    worker = PipelineWorker(runtime.repository)
    try:
        _initialize_runtime()
        while not stop.is_set():
            try:
                worked = worker.run_once(_run_pipeline_scheduler)
            except Exception:
                logger.exception('Worker polling failed')
                worked = False
            if not worked:
                stop.wait(5)
    finally:
        runtime.repository.close_pool()


if __name__ == '__main__':
    main()
