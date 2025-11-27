from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from core.config import settings
from domain.enums import ArtifactType, JobStatus
from services import annotator
from services import jobs as job_service
from services.state_manager import ProcessingStage, StateManager
from services.storage import prepare_job_dir
from services.wcs_utils import extract_calibration, parse_solver_stdout

logger = logging.getLogger(__name__)


def _build_cli_args(source_path: Path, job_dir: Path, upload_args: dict[str, Any]) -> list[str]:
    wcs_path = job_dir / "wcs.fits"
    new_fits_path = job_dir / "new.fits"
    corr_path = job_dir / "corr.fits"
    rdls_path = job_dir / "rdls.fits"
    match_path = job_dir / "match.fits"
    solved_path = job_dir / "solved.txt"

    args = [
        settings.solve_field_bin,
        str(source_path),
        "--overwrite",
        "--dir",
        str(job_dir),
        "--temp-dir",
        str(job_dir),
        "--index-dir",
        str(settings.astrometry_index_dir),
        "--wcs",
        str(wcs_path),
        "--new-fits",
        str(new_fits_path),
        "--corr",
        str(corr_path),
        "--rdls",
        str(rdls_path),
        "--match",
        str(match_path),
        "--solved",
        str(solved_path),
    ]

    if getattr(settings, "enable_kmz", False):
        kmz_path = job_dir / "sky.kmz"
        args += ["--kmz", str(kmz_path)]

    scale_units = upload_args.get("scale_units")
    if scale_units:
        args += ["--scale-units", str(scale_units)]
    if upload_args.get("scale_lower"):
        args += ["--scale-low", str(upload_args["scale_lower"])]
    if upload_args.get("scale_upper"):
        args += ["--scale-high", str(upload_args["scale_upper"])]
    if upload_args.get("center_ra"):
        args += ["--ra", str(upload_args["center_ra"])]
    if upload_args.get("center_dec"):
        args += ["--dec", str(upload_args["center_dec"])]
    if upload_args.get("radius"):
        args += ["--radius", str(upload_args["radius"])]
    if upload_args.get("downsample_factor"):
        args += ["--downsample", str(upload_args["downsample_factor"])]
    if upload_args.get("positional_error"):
        args += ["--pixel-error", str(upload_args["positional_error"])]
    if upload_args.get("tweak_order"):
        args += ["--tweak-order", str(upload_args["tweak_order"])]
    if upload_args.get("crpix_center"):
        args += ["--crpix-center"]
    if upload_args.get("invert"):
        args += ["--invert"]
    if upload_args.get("use_sextractor"):
        args += ["--use-source-extractor"]
    parity = upload_args.get("parity")
    if parity:
        args += ["--parity", "pos" if int(parity) >= 0 else "neg"]

    return args


async def solve_job(db: AsyncIOMotorDatabase, job_id: int, payload: dict[str, Any]) -> None:
    source_path = Path(payload["stored_path"])
    job_dir = prepare_job_dir(job_id)
    state = StateManager(job_dir)
    cli_args = _build_cli_args(source_path, job_dir, payload.get("upload_args", {}))

    # Initialize file system state
    state.update_stage(ProcessingStage.STARTED, "Job started, preparing...")

    logger.info("Running solve-field for job %s", job_id)
    state.update_stage(ProcessingStage.SOLVING, "Running solve-field...")

    # Run solve-field with streaming output to log file
    proc = await asyncio.create_subprocess_exec(
        *cli_args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
    )

    # Stream output to log file
    stdout_lines = []
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded_line = line.decode("utf-8", errors="ignore")
        stdout_lines.append(decoded_line)
        state.append_log(decoded_line)

    await proc.wait()
    stdout_text = "".join(stdout_lines)

    if proc.returncode != 0:
        error_msg = f"solve-field failed with exit code {proc.returncode}"
        logger.error("solve-field failed for job %s: %s", job_id, stdout_text)
        state.update_stage(ProcessingStage.FAILED, error_msg, error=stdout_text)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=stdout_text,
        )
        raise RuntimeError(f"solve-field failed: {stdout_text}")

    logger.info("solve-field job %s completed", job_id)

    # Verify that essential files were created
    wcs_path = job_dir / "wcs.fits"
    if not wcs_path.exists():
        error_msg = f"solve-field completed but wcs.fits not found for job {job_id}"
        logger.error(error_msg)
        state.update_stage(ProcessingStage.FAILED, error_msg, error=error_msg)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=error_msg,
        )
        raise RuntimeError(error_msg)

    # Update stage: calibrating
    state.update_stage(ProcessingStage.CALIBRATING, "Extracting calibration data...")

    solver_meta = parse_solver_stdout(stdout_text)

    calibration = None
    try:
        calibration = extract_calibration(
            job_dir / "new.fits",
            wcs_path,
            solver_meta.orientation,
            solver_meta.parity,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to compute calibration for job %s: %s", job_id, exc)

    results = {"original_filename": source_path.name}
    if calibration:
        results["calibration"] = calibration

    annotations = [
        {"text": text}
        for text in solver_meta.objects
    ]

    await job_service.update_job_status(
        db,
        job_id,
        JobStatus.success,
        results=results,
        annotations=annotations,
        objects_in_field=solver_meta.objects,
    )

    await job_service.add_artifact(db, job_id, ArtifactType.wcs, str(job_dir / "wcs.fits"))
    await job_service.add_artifact(db, job_id, ArtifactType.new_fits, str(job_dir / "new.fits"))
    await job_service.add_artifact(db, job_id, ArtifactType.corr, str(job_dir / "corr.fits"))
    if getattr(settings, "enable_kmz", False):
        await job_service.add_artifact(db, job_id, ArtifactType.kml, str(job_dir / "sky.kmz"))
    
    # Update stage: annotating
    state.update_stage(ProcessingStage.ANNOTATING, "Generating annotated image...")

    # Generate annotated image (only if WCS file exists)
    if not wcs_path.exists():
        logger.warning("Skipping annotated image generation for job %s: wcs.fits not found", job_id)
        annotated = annotator.generate_placeholder_annotation(job_id, source_path)
        logger.info("Using placeholder annotation for job %s: %s", job_id, annotated)
    else:
        radius = calibration.get("radius", 1.0) if calibration else 1.0
        logger.info("Starting annotated image generation for job %s with radius %s", job_id, radius)
        try:
            annotated = await annotator.generate_annotation(
                job_id, source_path, wcs_path, radius
            )
            logger.info("Annotated image generated successfully for job %s: %s", job_id, annotated)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to generate annotation for job %s: %s", job_id, exc, exc_info=True)
            annotated = annotator.generate_placeholder_annotation(job_id, source_path)
            logger.info("Using placeholder annotation for job %s: %s", job_id, annotated)
    await job_service.add_artifact(db, job_id, ArtifactType.annotated, str(annotated))
    logger.info("Annotated image artifact saved for job %s", job_id)

    # Update stage: completed
    state.update_stage(ProcessingStage.COMPLETED, "Job completed successfully")
