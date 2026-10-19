#!/usr/bin/env bash
# One-command setup for macOS. Safe to re-run: every step checks before it installs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"
# shellcheck source=lib/common.sh
source "$REPO_ROOT/scripts/lib/common.sh"

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

[ "$(uname -s)" = "Darwin" ] || warn "this script targets macOS; continuing anyway."

# 1. Homebrew --------------------------------------------------------------------------------
if ! command -v brew >/dev/null 2>&1; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$candidate" ]; then eval "$("$candidate" shellenv)"; break; fi
  done
fi
if command -v brew >/dev/null 2>&1; then
  ok "Homebrew $(brew --version | head -n1 | awk '{print $2}')"
else
  info "Installing Homebrew (asks for your password)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    if [ -x "$candidate" ]; then eval "$("$candidate" shellenv)"; break; fi
  done
  command -v brew >/dev/null 2>&1 || die "Homebrew install did not finish. Install it from https://brew.sh and re-run."
  warn "Add Homebrew to your shell: echo 'eval \"\$($(command -v brew) shellenv)\"' >> ~/.zprofile"
fi

# 2. git, uv, jq -----------------------------------------------------------------------------
brew_ensure() {
  local cmd="$1" formula="${2:-$1}"
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$cmd"
  else
    info "brew install $formula"
    brew install "$formula" >/dev/null || die "brew install $formula failed"
    ok "$cmd installed"
  fi
}
# /usr/bin/git is a stub that prompts for Xcode tools when they are missing; test it really runs.
if git --version >/dev/null 2>&1; then ok "git"; else brew_ensure git; fi
brew_ensure uv
brew_ensure jq
if [ "${WITH_DEV_TOOLS:-1}" = "1" ]; then brew_ensure shellcheck; fi

# 3. Python via uv + venv + deps ---------------------------------------------------------------
info "Python $PYTHON_VERSION via uv"
uv python install "$PYTHON_VERSION" >/dev/null 2>&1 || die "uv python install $PYTHON_VERSION failed"
info "Creating .venv and installing dependencies (uv sync)"
uv sync --python "$PYTHON_VERSION" --quiet || die "uv sync failed; see the error above"
ok "virtualenv at .venv ($(uv run --quiet python --version))"

# 4. Distil CLI --------------------------------------------------------------------------------
if command -v distil >/dev/null 2>&1; then
  ok "distil $(distil --version 2>/dev/null)"
else
  info "Installing the Distil CLI to ~/.local/bin"
  curl -fsSL https://cli-assets.distillabs.ai/install.sh | sh \
    || die "Distil CLI install failed. Try manually: curl -fsSL https://cli-assets.distillabs.ai/install.sh | sh"
  command -v distil >/dev/null 2>&1 || die "distil installed but not on PATH; open a new terminal and re-run."
  ok "distil $(distil --version 2>/dev/null)"
fi

# 5. .env --------------------------------------------------------------------------------------
if [ -f .env ]; then
  ok ".env exists (left untouched)"
else
  cp .env.example .env
  ok "created .env from .env.example"
fi

mkdir -p runs data/raw

# 6. Next steps --------------------------------------------------------------------------------
distil_user="$(distil whoami --output json 2>/dev/null | jq -r '.email // .username // empty' 2>/dev/null || true)"
cat <<EOF

${C_BLD}Setup done. Next steps:${C_OFF}

  1. Distil Labs login $( [ -n "$distil_user" ] && printf '(already logged in as %s)' "$distil_user" )
       distil auth          # existing account (opens a browser)
       distil signup        # new account
  2. Fill in .env (open it in your editor):
       LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST   Langfuse -> Settings -> API Keys
       SERVE_BASE_URL / SERVE_API_KEY / RUNPOD_GPU_USD_PER_HOUR    after the pod is up (serve/README.md)
       TEACHER_*                                                   optional, for teacher latency/cost
  3. Verify everything:
       make check
  4. Optional, for Claude Code users: the Distil skill
       distil skill install
     or inside Claude Code:
       /plugin marketplace add https://github.com/distil-labs/distil-cli-skill

  New terminal? ~/.local/bin must be on PATH for 'distil' (the installer adds it to ~/.zshrc).
EOF
