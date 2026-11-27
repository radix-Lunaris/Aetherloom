"""Build a checked Anvil cleanup plan on a separate world copy."""
from pathlib import Path
import shutil
import stat
import tempfile
from uuid import uuid4
from .vendor.mcsync import chunk_prune
from .world_lock import closed_world


def clean_copy(world, threshold, confirm=None, *, dimensions=None, report_only=False, in_place=False):
    world = Path(world).resolve()
    with closed_world(world):
        files = list(world.rglob('*'))
        if any(item.is_symlink() or getattr(item.lstat(),'st_file_attributes',0) & stat.FILE_ATTRIBUTE_REPARSE_POINT for item in files):
            raise ValueError('存档包含链接目录或文件，无法安全清理')
        report = chunk_prune.scan(str(world), threshold_seconds=threshold, selected_dims=dimensions)
        if not report.supported:
            raise ValueError(report.unsupported_reason)
        # A region and its entities/POI companions must remain in sync.
        protected = {
            (item.dimension, Path(item.path).name)
            for item in report.regions
            if not item.verdicts or any(
                verdict.reason in ('skip:external','skip:truncated')
                for verdict in item.verdicts.values()
            )
        }
        for item in report.regions:
            if item.prune and item.kind!='region' and item.unreadable:
                # Upstream aligns companion verdicts to terrain and may
                # overwrite the original external-sector marker.
                parsed=chunk_prune.parse_region(item.path,report.threshold_ticks,keep_data=False)
                if any(v.reason in ('skip:external','skip:truncated') for v in parsed.verdicts.values()):
                    protected.add((item.dimension,Path(item.path).name))
        plans = {
            Path(item.path).resolve().relative_to(world): tuple(sorted(
                index for index, verdict in item.verdicts.items() if verdict.reason == 'prune'
            ))
            for item in report.regions
            if item.prune and (item.dimension, Path(item.path).name) not in protected
        }
        identity = {
            path: (indexes, (world/path).stat().st_size, (world/path).stat().st_mtime_ns)
            for path,indexes in plans.items()
        }
        if confirm is None:
            return (identity, report) if report_only else identity
        if identity != confirm or not plans:
            raise ValueError('清理候选已变化，请重新预览')
        if in_place:
            # Use upstream's full backup and apply path only on files proven safe.
            confirmed=[]
            for item in report.regions:
                path=Path(item.path).resolve().relative_to(world)
                if path in plans:
                    confirmed.append(item)
            report.regions=confirmed
            report.prune_chunks=sum(item.prune for item in confirmed if item.kind=="region")
            return chunk_prune.apply(report)
        name = 'Aetherloom-Pruned-' + uuid4().hex[:12]
        final = world.parent / name
        with tempfile.TemporaryDirectory(prefix='.'+name+'-',dir=world.parent) as work:
            scratch = Path(work)/'world'
            shutil.copytree(world, scratch, ignore=shutil.ignore_patterns('.aetherloom','session.lock'))
            for path, indexes in plans.items():
                target = scratch/path
                region = chunk_prune.parse_region(str(target), report.threshold_ticks, keep_data=True)
                if not set(indexes).issubset(region.verdicts):
                    raise ValueError('清理副本的区块索引与预览不一致')
                if any(not chunk.data or chunk.reason in ('skip:external','skip:truncated')
                       for chunk in region.verdicts.values()):
                    raise ValueError('清理副本包含无法安全重写的区块')
                for index, chunk in region.verdicts.items():
                    chunk.reason = 'prune' if index in indexes else 'keep'
                chunk_prune.rewrite_region(str(target), region.verdicts)
            scratch.rename(final)
        return final
