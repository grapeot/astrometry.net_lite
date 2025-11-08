from __future__ import annotations

import asyncio
import logging

from services import queue as queue_service
from services.mongo import create_mongo_client, get_database
from services import jobs as job_service
from services import solver_bridge
from domain.enums import JobStatus, SubmissionStatus
from services import submissions as submission_service

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
logger = logging.getLogger("worker")


async def process_loop():
    client = create_mongo_client()
    db = get_database(client)
    try:
        while True:
            msg = await queue_service.lease_job(db)
            if not msg:
                await asyncio.sleep(2)
                continue
            job_id = msg.job_id
            logger.info("Processing job %s", job_id)
            try:
                submission_id = msg.payload.get("submission_id")
                if submission_id:
                    await submission_service.mark_submission_started(db, submission_id)
                await job_service.mark_job_started(db, job_id)
                await solver_bridge.solve_job(db, job_id, msg.payload)
                if submission_id:
                    await submission_service.mark_submission_finished(db, submission_id, SubmissionStatus.success)
                await queue_service.complete_job(db, msg.id)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Job %s failed: %s", job_id, exc)
                await job_service.update_job_status(db, job_id, JobStatus.failure, failure_reason=str(exc))
                submission_id = msg.payload.get("submission_id")
                if submission_id:
                    await submission_service.mark_submission_finished(db, submission_id, SubmissionStatus.failure)
                await queue_service.fail_job(db, msg.id, str(exc))
    finally:
        client.close()


def main():
    asyncio.run(process_loop())


if __name__ == "__main__":
    main()
