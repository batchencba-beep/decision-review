#!/usr/bin/env bash
# One-time setup for the video-edit skill. Safe to re-run.
#   bash setup.sh              install everything and pre-download the Hebrew model
#   bash setup.sh --no-model   skip the ~1.6 GB model download (it downloads on first use)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; exit 1; }

echo "video-edit setup"
command -v ffmpeg  >/dev/null || fail "ffmpeg not found (macOS: brew install ffmpeg · Ubuntu: apt install ffmpeg)"
command -v ffprobe >/dev/null || fail "ffprobe not found (comes with ffmpeg)"
FILTERS="$(ffmpeg -hide_banner -filters 2>/dev/null)"; ENCODERS="$(ffmpeg -hide_banner -encoders 2>/dev/null)"
grep -q " zscale " <<<"$FILTERS" || fail "ffmpeg lacks zscale (needed for HDR tone-mapping); install a full build"
grep -q prores_ks <<<"$ENCODERS" || fail "ffmpeg lacks the prores_ks encoder"
grep -q libx264 <<<"$ENCODERS"   || fail "ffmpeg lacks libx264"
ok "ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}')"

command -v python3 >/dev/null || fail "python3 not found"
python3 -c 'import sys; assert sys.version_info >= (3, 10)' || fail "python ≥ 3.10 required"
python3 -m pip install --quiet -r "$HERE/requirements.txt" || fail "pip install failed"
ok "python packages (faster-whisper, numpy)"

command -v node >/dev/null || fail "node not found (≥ 18; macOS: brew install node)"
(cd "$SKILL/remotion" && npm install --no-audit --no-fund --silent) || fail "npm install failed in remotion/"
ok "remotion $(cd "$SKILL/remotion" && node -p 'require("remotion/package.json").version')"

if [[ "${1:-}" != "--no-model" ]]; then
  python3 - <<'PY' || fail "model download failed"
from huggingface_hub import snapshot_download
snapshot_download("ivrit-ai/whisper-large-v3-turbo-ct2")
PY
  ok "Hebrew Whisper model (ivrit-ai/whisper-large-v3-turbo-ct2)"
fi
echo "ready."
