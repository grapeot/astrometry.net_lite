from __future__ import annotations

import asyncio
import logging
import shutil
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


def check_tools_available() -> tuple[bool, str]:
    """
    Check if augment-xylist (or solve-field) and astrometry-engine tools are available.
    
    First checks if the configured path exists, then falls back to PATH lookup.
    If augment-xylist is not found, checks if solve-field is available as a fallback.
    
    Returns:
        Tuple of (is_available, error_message)
        If available, error_message is empty string.
        If not available, error_msg contains helpful installation instructions.
    """
    missing_tools = []
    
    # Check augment-xylist or solve-field (fallback)
    augment_xylist_path = Path(settings.augment_xylist_bin)
    augment_xylist_found = augment_xylist_path.exists() or shutil.which("augment-xylist")
    
    if not augment_xylist_found:
        # Check if solve-field is available as fallback
        solve_field_path = Path(settings.solve_field_bin)
        solve_field_found = solve_field_path.exists() or shutil.which("solve-field")
        if not solve_field_found:
            missing_tools.append(("augment-xylist or solve-field", settings.augment_xylist_bin, "AUGMENT_XYLIST_BIN or SOLVE_FIELD_BIN"))
    
    # Check astrometry-engine
    engine_path = Path(settings.astrometry_engine_bin)
    if not engine_path.exists():
        found_in_path = shutil.which("astrometry-engine")
        if not found_in_path:
            missing_tools.append(("astrometry-engine", settings.astrometry_engine_bin, "ASTROMETRY_ENGINE_BIN"))
    
    if missing_tools:
        tool_names = ", ".join(tool[0] for tool in missing_tools)
        paths = "\n".join(f"  - {tool[0]}: {tool[1]}" for tool in missing_tools)
        env_vars = ", ".join(tool[2] for tool in missing_tools)
        error_msg = (
            f"The astrometry tool(s) '{tool_names}' not found.\n\n"
            f"Configured paths:\n{paths}\n\n"
            "Please install astrometry.net:\n"
            "  - macOS: brew install astrometry-net\n"
            "  - Linux: apt-get install astrometry.net\n"
            f"  - Or set {env_vars} environment variable(s) to point to the correct path(s)"
        )
        return False, error_msg
    
    return True, ""


def _get_tool_path(configured_path: str, tool_name: str) -> str:
    """Get tool path, falling back to PATH lookup if configured path doesn't exist."""
    path = Path(configured_path)
    if path.exists():
        return str(path)
    # Fall back to PATH lookup
    found = shutil.which(tool_name)
    if found:
        return found
    # Return configured path anyway - error will be caught during execution
    return configured_path


def _build_augment_xylist_args(source_path: Path, job_dir: Path, upload_args: dict[str, Any]) -> list[str]:
    """Build command-line arguments for augment-xylist.
    
    Uses solve-field --just-augment if augment-xylist is not available,
    as some distributions package solve-field but not augment-xylist separately.
    """
    axy_path = job_dir / "job.axy"
    wcs_path = job_dir / "wcs.fits"
    corr_path = job_dir / "corr.fits"
    rdls_path = job_dir / "rdls.fits"
    
    # Resolve index directory to absolute path
    index_dir = settings.astrometry_index_dir.resolve()
    
    # Try to use augment-xylist if available, otherwise fall back to solve-field --just-augment
    augment_xylist_path = _get_tool_path(settings.augment_xylist_bin, "augment-xylist")
    use_solve_field = False
    
    if not Path(augment_xylist_path).exists() and not shutil.which("augment-xylist"):
        # Fall back to solve-field --just-augment
        solve_field_path = _get_tool_path(settings.solve_field_bin, "solve-field")
        if Path(solve_field_path).exists() or shutil.which("solve-field"):
            use_solve_field = True
            args = [
                solve_field_path if Path(solve_field_path).exists() else "solve-field",
                "--just-augment",
                "--axy", str(axy_path),
                "--dir", str(job_dir),
                "--temp-dir", str(job_dir),
                "--index-dir", str(index_dir.resolve()),  # Use absolute path for index directory
                "--objs", "1000",  # Limit to 1000 sources for faster processing
            ]
        else:
            # Neither available, use configured path (will fail with helpful error)
            args = [augment_xylist_path]
    else:
        # Use augment-xylist
        args = [
            augment_xylist_path,
            "--out", str(axy_path),
            "--image", str(source_path),
            "--wcs", str(wcs_path),
            "--corr", str(corr_path),
            "--rdls", str(rdls_path),
            "--tag-all",
            "--objs", "1000",
        ]
    
    # Add common parameters (both augment-xylist and solve-field support these)
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
    # Default to downsample 2 if not specified (for faster processing)
    downsample = upload_args.get("downsample_factor", 2)
    args += ["--downsample", str(downsample)]
    if upload_args.get("positional_error"):
        args += ["--pixel-error", str(upload_args["positional_error"])]
    tweak_order = upload_args.get("tweak_order")
    if tweak_order is not None:
        if tweak_order == 0:
            args += ["--no-tweak"]
        else:
            args += ["--tweak-order", str(tweak_order)]
    if upload_args.get("crpix_center"):
        args += ["--crpix-center"]
    if upload_args.get("invert"):
        args += ["--invert"]
    if upload_args.get("use_sextractor"):
        args += ["--use-source-extractor"]
    parity = upload_args.get("parity")
    if parity is not None:
        args += ["--parity", "pos" if int(parity) >= 0 else "neg"]
    
    # Add source image and output file specifications
    if use_solve_field:
        # For solve-field --just-augment, add output file options and source image
        # Note: solve-field accepts source image as positional argument
        args += [
            "--wcs", str(wcs_path),
            "--corr", str(corr_path),
            "--rdls", str(rdls_path),
            str(source_path),  # Positional argument for solve-field
        ]
    # For augment-xylist, --image was already added above, no need to add again
    
    return args


def _ensure_config_file(job_dir: Path) -> Path:
    """Ensure astrometry.cfg file exists with proper index configuration.
    
    Creates a config file that explicitly lists all index files and enables
    inparallel mode for better performance.
    
    IMPORTANT: This config file ONLY lists indexes from our configured directory,
    avoiding system default indexes that might interfere.
    """
    config_path = job_dir / "astrometry.cfg"
    
    # Only create if it doesn't exist or is older than index directory
    index_dir = settings.astrometry_index_dir.resolve()
    if config_path.exists():
        config_mtime = config_path.stat().st_mtime
        # Check if any index file is newer than config
        try:
            for idx_file in index_dir.glob("*.fits"):
                if idx_file.stat().st_mtime > config_mtime:
                    # Index file is newer, regenerate config
                    break
            else:
                # No newer index files, use existing config
                return config_path
        except Exception:
            # If we can't check, regenerate to be safe
            pass
    
    # Generate config file
    # IMPORTANT: Use absolute paths and only list .fits files (not .fits.gz)
    # This ensures we only use our configured indexes, not system defaults
    with open(config_path, "w") as f:
        # Use absolute path to avoid confusion with system paths
        f.write(f"add_path {index_dir}\n")
        
        # List all .fits files explicitly (exclude .fits.gz as they're not valid)
        # Sort to ensure consistent order
        index_files = sorted([f for f in index_dir.glob("*.fits") if not f.name.endswith(".gz")])
        for idx_file in index_files:
            # Use absolute path to ensure we use the right index
            f.write(f"index {idx_file.name}\n")
        
        # Enable parallel index checking for better performance
        # This is safe if indexes fit in memory
        f.write("inparallel\n")
    
    logger.debug("Generated astrometry config file: %s with %d indexes", config_path, len(index_files))
    return config_path


def _build_astrometry_engine_args(job_dir: Path, job_id: int) -> list[str]:
    """Build command-line arguments for astrometry-engine.
    
    Uses config file if possible for better performance (explicit index listing + inparallel).
    Falls back to -I directory if config file generation fails.
    """
    axy_path = job_dir / "job.axy"
    solved_path = job_dir / "solved.txt"
    
    # Use config file for better performance
    # This ensures we only use our configured indexes, not system defaults
    try:
        config_path = _ensure_config_file(job_dir)
        args = [
            _get_tool_path(settings.astrometry_engine_bin, "astrometry-engine"),
            "-v",  # verbose
            "-c", str(config_path),  # Use config file (explicit indexes + inparallel)
            "-s", str(solved_path),  # solved file
            "-j", f"job-{job_id}",  # job ID (for logging)
            str(axy_path),  # input axy file
        ]
        logger.debug("Using config file %s for astrometry-engine", config_path)
    except Exception as e:
        # Fall back to -I directory if config file generation fails
        # But explicitly exclude system paths to avoid loading wrong indexes
        logger.warning("Failed to generate config file, falling back to -I directory: %s", e)
        index_dir = settings.astrometry_index_dir.resolve()
        args = [
            _get_tool_path(settings.astrometry_engine_bin, "astrometry-engine"),
            "-v",  # verbose
            "-I", str(index_dir.resolve()),  # index directory (absolute path)
            "-s", str(solved_path),  # solved file
            "-j", f"job-{job_id}",  # job ID (for logging)
            str(axy_path),  # input axy file
        ]
        logger.warning("Using -I directory fallback (may load system default indexes)")
    
    return args


async def solve_job(db: AsyncIOMotorDatabase, job_id: int, payload: dict[str, Any]) -> None:
    source_path = Path(payload["stored_path"])
    job_dir = prepare_job_dir(job_id)
    state = StateManager(job_dir)
    
    # Check if tools are available before starting
    is_available, error_msg = check_tools_available()
    if not is_available:
        logger.error("Astrometry tools not available for job %s: %s", job_id, error_msg)
        state.update_stage(ProcessingStage.FAILED, "Astrometry solver tools not found", error=error_msg)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=error_msg,
        )
        raise RuntimeError(error_msg)

    # Initialize file system state
    state.update_stage(ProcessingStage.STARTED, "Job started, preparing...")

    # Step 1: Run augment-xylist to create job.axy file
    logger.info("Running augment-xylist for job %s", job_id)
    state.update_stage(ProcessingStage.SOLVING, "Extracting sources with augment-xylist...")
    
    augment_args = _build_augment_xylist_args(source_path, job_dir, payload.get("upload_args", {}))
    
    try:
        augment_proc = await asyncio.create_subprocess_exec(
            *augment_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as e:
        error_msg = (
            f"Failed to execute augment-xylist: {e}\n\n"
            "The astrometry tool may not be installed or not in PATH.\n"
            "Please install astrometry.net:\n"
            "  - macOS: brew install astrometry-net\n"
            "  - Linux: apt-get install astrometry.net"
        )
        logger.error("augment-xylist execution failed for job %s: %s", job_id, error_msg)
        state.update_stage(ProcessingStage.FAILED, "augment-xylist not found", error=error_msg)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=error_msg,
        )
        raise RuntimeError(error_msg) from e

    # Stream augment-xylist output
    augment_stdout_lines = []
    while True:
        line = await augment_proc.stdout.readline()
        if not line:
            break
        decoded_line = line.decode("utf-8", errors="ignore")
        augment_stdout_lines.append(decoded_line)
        state.append_log(decoded_line)

    await augment_proc.wait()
    augment_stdout_text = "".join(augment_stdout_lines)

    if augment_proc.returncode != 0:
        error_msg = f"augment-xylist failed with exit code {augment_proc.returncode}"
        logger.error("augment-xylist failed for job %s: %s", job_id, augment_stdout_text)
        state.update_stage(ProcessingStage.FAILED, error_msg, error=augment_stdout_text)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=augment_stdout_text,
        )
        raise RuntimeError(f"augment-xylist failed: {augment_stdout_text}")

    logger.info("augment-xylist completed for job %s", job_id)
    
    # Verify axy file was created
    axy_path = job_dir / "job.axy"
    if not axy_path.exists():
        error_msg = f"augment-xylist completed but job.axy not found for job {job_id}"
        logger.error(error_msg)
        state.update_stage(ProcessingStage.FAILED, error_msg, error=error_msg)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=error_msg,
        )
        raise RuntimeError(error_msg)

    # Step 2: Run astrometry-engine to solve the field
    logger.info("Running astrometry-engine for job %s", job_id)
    state.update_stage(ProcessingStage.SOLVING, "Solving field with astrometry-engine...")
    
    engine_args = _build_astrometry_engine_args(job_dir, job_id)
    
    try:
        engine_proc = await asyncio.create_subprocess_exec(
            *engine_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError as e:
        error_msg = (
            f"Failed to execute astrometry-engine: {e}\n\n"
            "The astrometry tool may not be installed or not in PATH.\n"
            "Please install astrometry.net:\n"
            "  - macOS: brew install astrometry-net\n"
            "  - Linux: apt-get install astrometry.net"
        )
        logger.error("astrometry-engine execution failed for job %s: %s", job_id, error_msg)
        state.update_stage(ProcessingStage.FAILED, "astrometry-engine not found", error=error_msg)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=error_msg,
        )
        raise RuntimeError(error_msg) from e

    # Stream astrometry-engine output
    engine_stdout_lines = []
    while True:
        line = await engine_proc.stdout.readline()
        if not line:
            break
        decoded_line = line.decode("utf-8", errors="ignore")
        engine_stdout_lines.append(decoded_line)
        state.append_log(decoded_line)

    await engine_proc.wait()
    engine_stdout_text = "".join(engine_stdout_lines)
    stdout_text = augment_stdout_text + "\n" + engine_stdout_text

    if engine_proc.returncode != 0:
        error_msg = f"astrometry-engine failed with exit code {engine_proc.returncode}"
        logger.error("astrometry-engine failed for job %s: %s", job_id, engine_stdout_text)
        state.update_stage(ProcessingStage.FAILED, error_msg, error=engine_stdout_text)
        await job_service.update_job_status(
            db,
            job_id,
            JobStatus.failure,
            failure_reason=engine_stdout_text,
        )
        raise RuntimeError(f"astrometry-engine failed: {engine_stdout_text}")

    logger.info("astrometry-engine completed for job %s", job_id)

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
