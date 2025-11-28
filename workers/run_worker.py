from __future__ import annotations

import asyncio
import logging

from domain.enums import JobStatus, SubmissionStatus
from services import jobs as job_service
from services import queue as queue_service
from services import solver_bridge
from services import submissions as submission_service
from services.mongo import create_mongo_client, get_database
from services.state_manager import ProcessingStage, StateManager
from services.storage import prepare_job_dir

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
logger = logging.getLogger("worker")


async def recover_incomplete_jobs(db) -> int:
    """
    Recover all incomplete jobs on worker startup.

    Finds jobs with status=solving in MongoDB and attempts to recover them
    based on file system state.

    Returns:
        Number of jobs recovered/reset
    """
    recovered = 0
    cursor = db["jobs"].find({
        "status": JobStatus.solving.value,
        "finished_at": None
    })

    async for doc in cursor:
        job_id = doc["job_id"]
        job_dir = prepare_job_dir(job_id)
        state = StateManager(job_dir)
        file_status = state.get_status()

        if file_status:
            stage = file_status.get("stage")
            logger.info(
                "Found incomplete job %s at stage '%s', will be reprocessed",
                job_id, stage
            )
            # For now, reset to queued and let it be reprocessed
            # A more sophisticated recovery could continue from the current stage
            await job_service.update_job_status(db, job_id, JobStatus.queued)
            state.clear_log()
            state.update_stage(ProcessingStage.STARTED, "Job requeued after worker restart")
        else:
            # No file status, reset to queued
            logger.warning(
                "Job %s has MongoDB status=solving but no file status, resetting to queued",
                job_id
            )
            await job_service.update_job_status(db, job_id, JobStatus.queued)

        recovered += 1

    return recovered


async def process_loop():
    client = create_mongo_client()
    db = get_database(client)
    try:
        # Check if solve-field tool is available on startup
        is_available, error_msg = solver_bridge.check_solve_field_available()
        if not is_available:
            logger.warning(
                "solve-field tool not available. Jobs will fail with helpful error messages.\n%s",
                error_msg
            )
        else:
            logger.info("solve-field tool is available and ready")
        
        # Recover incomplete jobs on startup
        recovered = await recover_incomplete_jobs(db)
        if recovered > 0:
            logger.info("Recovered %d incomplete jobs", recovered)

        while True:
            msg = await queue_service.lease_job(db)
            if not msg:
                await asyncio.sleep(2)
                continue
            job_id = msg.job_id
            logger.info("Processing job %s", job_id)

            # Initialize state manager for error handling
            job_dir = prepare_job_dir(job_id)
            state = StateManager(job_dir)

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
                # Update file system state
                state.update_stage(
                    ProcessingStage.FAILED,
                    f"Job failed: {exc}",
                    error=str(exc)
                )
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
