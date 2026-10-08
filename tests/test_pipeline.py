import shutil
from pathlib import Path

import pytest

from videomaker import media, pipeline
from videomaker.lint import lint
from videomaker.plan import plan_segments, split_duration
from videomaker.prompt import video_prompt
from videomaker.providers.mock import MockProvider
from videomaker.schema import Project, load_project

EXAMPLE = Path(__file__).parent.parent / "projects" / "example-rain-cat"


def test_split_duration():
    assert split_duration(6, 15) == [6]
    assert split_duration(20, 15) == [10, 10]
    assert split_duration(31, 15) == [11, 10, 10]
    assert all(d <= 15 for d in split_duration(44, 15))


def test_plan_segments_chain_continuations():
    p = load_project(EXAMPLE)
    segs = plan_segments(p, 15)
    assert [s.key for s in segs] == ["s01", "s02.1", "s02.2", "s03"]
    assert segs[1].start_frame == "keyframe"
    assert segs[2].start_frame == "chain" and segs[2].is_continuation
    assert "紧接首帧画面继续" in video_prompt(p, segs[2])


def test_schema_rejects_unknown_character():
    with pytest.raises(ValueError):
        Project.model_validate({"id": "x", "title": "x", "shots": [
            {"id": "a", "duration": 3, "action": "x", "characters": ["ghost"]}]})


def test_lint_flags_missing_refs():
    warnings = lint(load_project(EXAMPLE))
    assert any("设定图" in w for w in warnings)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg")
def test_mock_render_and_assemble(tmp_path):
    shutil.copytree(EXAMPLE, tmp_path / "proj")
    p = load_project(tmp_path / "proj")
    p.output.resolution = "480p"
    prov = MockProvider()
    clips = pipeline.render(p, prov, log=lambda _: None)
    assert len(clips) == 4

    # 再跑一次全部跳过（断点续跑）
    logs = []
    pipeline.render(p, prov, log=logs.append)
    assert all(l.startswith("[跳过]") for l in logs)

    # 重拍 s02.1 → 依赖它尾帧的 s02.2 也重新生成，s03 用自己的关键帧所以不受影响
    logs = []
    pipeline.render(p, prov, retake={"s02.1"}, log=logs.append)
    regenerated = [l.split()[1] for l in logs if l.startswith("[生成]")]
    assert regenerated == ["s02.1", "s02.2"]
    assert any((p.output_dir / "takes").iterdir())

    final = pipeline.assemble(p, log=lambda _: None)
    assert abs(media.duration(final) - 32) < 1.0
    assert (p.output_dir / "rain-cat.srt").exists()
    assert (p.output_dir / "publish" / "douyin.json").exists()
