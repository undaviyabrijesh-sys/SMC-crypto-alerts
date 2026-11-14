"""Contract checks for the manually dispatched visual-paper workflow."""
from pathlib import Path


workflow = Path(".github/workflows/tools.yml").read_text(encoding="utf-8")

assert "confirm_visual_paper:" in workflow
assert "type: boolean" in workflow
assert "default: false" in workflow
assert 'if [ "${{ inputs.confirm_visual_paper }}" != "true" ]; then' in workflow
assert "ENABLE_VISUAL_PAPER=true python visual_worker.py" in workflow
assert "run: python main.py" not in workflow
assert "VISUAL_FIRST_RESEARCH_PATH:" in workflow
assert "VISUAL_FIRST_CHART_DIR:" in workflow
assert "actions/upload-artifact@v4" in workflow
assert "path: visual_artifacts/" in workflow

print("PASS manual visual workflow routes to the confirmed visual worker and uploads audit evidence")
